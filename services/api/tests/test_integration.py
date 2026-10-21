"""End-to-end integration tests (v0.14): the full review pipeline against a
REAL Postgres — migrations applied by the actual runner, then HTTP calls
through the real FastAPI app (real SQL, real enum casts, real triggers).

This is the layer that would have caught every SQL/enum bug that unit tests
with fakes cannot see: /analytics aggregates, state-machine UPDATEs, evidence
domain checks, JSONB round-trips.

Requires a disposable database:
    MTK_TEST_DATABASE_URL=postgresql://... pytest services/api/tests/test_integration.py

The schema is WIPED (public) at start — never point this at a database you
care about. Skipped automatically when the env var is absent.
"""

import asyncio
import os

import pytest

REQUIRED_ENV = "MTK_TEST_DATABASE_URL"

if not os.environ.get(REQUIRED_ENV):
    pytest.skip(
        f"integration tests need {REQUIRED_ENV} pointing at a DISPOSABLE database",
        allow_module_level=True,
    )

import asyncpg
from fastapi.testclient import TestClient

import db_migrate

DSN = os.environ[REQUIRED_ENV]


# ------------------------------------------------------------- fixtures

@pytest.fixture(scope="session")
def client():
    """Wiped schema + migrations applied by the real runner + the real app."""

    async def _reset_and_migrate():
        admin = await asyncpg.connect(DSN)
        try:
            await admin.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        finally:
            await admin.close()
        return await db_migrate.apply_all(DSN)

    summary = asyncio.run(_reset_and_migrate())
    assert len(summary["applied"]) == summary["total_known"] > 0

    os.environ["DATABASE_URL"] = DSN
    import main  # reads DATABASE_URL at import; startup() builds the pool

    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def source(client):
    """A Tier-A provider whose canonical domain covers example.com."""
    res = client.post("/sources", json={
        "provider": "Acme Domains",
        "canonical_domain": "example.com",
        "category": "domains",
        "adapter": "manual",
        "trust_tier": "A_provider_owned",
    })
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ------------------------------------------------------------- the pipeline

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_full_review_pipeline(client, source):
    # ---- ingest: dedup guarantee (master plan §18 week 2 -------------------
    item_body = {
        "source_id": source,
        "external_item_id": "acme-2026-11-01",
        "url": "https://example.com/free-domain-2026",
        "title": "One-year .example domain free for new customers",
        "text": "Twelve months free, then standard renewal. New accounts only.",
    }
    first = client.post("/items", json=item_body)
    assert first.status_code == 201, first.text
    assert first.json()["created"] is True and first.json()["duplicate"] is False

    second = client.post("/items", json=item_body)
    assert second.status_code == 201
    assert second.json()["duplicate"] is True
    assert second.json()["id"] == first.json()["id"], "same canonical item must dedupe"

    # ---- inbox listing -----------------------------------------------------
    inbox = client.get("/items", params={"processed": "false"})
    assert inbox.status_code == 200
    titles = [row["title"] for row in inbox.json()]
    assert "One-year .example domain free for new customers" in titles

    # ---- promote: inbox → review desk --------------------------------------
    promo = client.post(f"/offers/from-item/{first.json()['id']}", json={
        "provider": "Acme Domains",
        "category": "domains",
        "offer_type": "discount",
    })
    assert promo.status_code == 201, promo.text
    offer_id = promo.json()["id"]

    # ---- state machine gates (§3: verified is earned, never asserted) ------
    early = client.post(f"/offers/{offer_id}/transition", json={"to": "verified"})
    assert early.status_code in (409, 422), "candidate cannot jump straight to verified"

    step1 = client.post(f"/offers/{offer_id}/transition", json={"to": "evidence_needed"})
    assert step1.status_code == 200, step1.text

    # legal stage, unmet gate: evidence_needed → verified must list its reasons
    ungated = client.post(f"/offers/{offer_id}/transition", json={"to": "verified"})
    assert ungated.status_code == 422, ungated.text
    assert "official" in ungated.json()["detail"]

    bad_domain = client.post(f"/offers/{offer_id}/evidence", json={
        "url": "https://not-our-domain.example.net/terms",
        "official": True,
        "excerpt": "12 months free for new accounts",
    })
    assert bad_domain.status_code == 422, "official evidence off the provider's domain must be refused"

    ev = client.post(f"/offers/{offer_id}/evidence", json={
        "url": "https://example.com/terms/free-domain",
        "official": True,
        "excerpt": "Twelve months free, then standard renewal. New accounts only.",
        "supported_fields": ["value", "eligibility"],
    })
    assert ev.status_code == 201, ev.text
    assert ev.json()["domain_ok"] is True and ev.json()["created"] is True

    # extraction: every field maps to its evidence URL (complete = True)
    ext = client.post(f"/offers/{offer_id}/extraction", json={
        "fields": {
            "value": {"value": "12 months free", "evidence_url": "https://example.com/terms/free-domain"},
            "eligibility": {"value": "new accounts", "evidence_url": "https://example.com/terms/free-domain"},
        },
        "complete": True,
        "model": "pytest",
    })
    assert ext.status_code == 201, ext.text

    verified = client.post(f"/offers/{offer_id}/transition",
                           json={"to": "verified", "reviewer": "pytest"})
    assert verified.status_code == 200, verified.text
    assert verified.json()["state"] == "verified"
    assert verified.json()["previous"] == "evidence_needed"

    # illegal jumps are refused (candidate can never skip to published)
    fresh = client.post("/items", json={
        "source_id": source,
        "external_item_id": "acme-2026-11-02",
        "url": "https://example.com/other-promo",
        "title": "Other promo",
    })
    promo2 = client.post(f"/offers/from-item/{fresh.json()['id']}", json={
        "provider": "Acme Domains", "category": "domains", "offer_type": "credits",
    })
    jump = client.post(f"/offers/{promo2.json()['id']}/transition",
                       json={"to": "published", "reviewer": "pytest"})
    assert jump.status_code == 409, "state machine must refuse skipped stages"

    # ---- analytics aggregates see all of it (§7) ---------------------------
    analytics = client.get("/analytics")
    assert analytics.status_code == 200, analytics.text
    data = analytics.json()
    by_state = {row["state"]: row["n"] for row in data["offers_by_state"]}
    assert by_state.get("verified", 0) >= 1
    assert data["items_total"] >= 2
    assert "generated_at" in data

    # evidence depth is per-offer, null-safe (v0.12 fixed the round-trip)
    assert data["verification"] is not None
    assert data["verification"]["evidence_per_offer"] is None \
        or data["verification"]["evidence_per_offer"] >= 0

    # ---- reviewer workflow -------------------------------------------------
    approve = client.post(f"/offers/{offer_id}/transition",
                          json={"to": "approved_for_video", "reviewer": "pytest"})
    assert approve.status_code == 200, approve.text

    no_reviewer = client.post(f"/offers/{offer_id}/transition",
                              json={"to": "published", "reviewer": None})
    assert no_reviewer.status_code == 403, "publishing demands a recorded reviewer"

    # ---- inbox processed flag ----------------------------------------------
    patch = client.patch(f"/items/{first.json()['id']}/processed", params={"processed": "true"})
    assert patch.status_code == 200
