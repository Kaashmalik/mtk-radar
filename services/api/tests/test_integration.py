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
import base64
import hashlib
import importlib.util
import json
import os
import sys as _sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit as url_split

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
from fetch_attestation import sign_provenance

DSN = os.environ[REQUIRED_ENV]


# ------------------------------------------------------------- fixtures

def _import_api_main():
    """Import services/api/main.py as 'api_main'. A bare `import main` is
    unreliable in combined test runs: pytest imports every test module before
    running any, and worker test modules have their own main.py cached under
    the same name."""
    if "api_main" in _sys.modules:
        return _sys.modules["api_main"]
    spec = importlib.util.spec_from_file_location(
        "api_main", Path(__file__).resolve().parents[1] / "main.py")
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["api_main"] = mod
    spec.loader.exec_module(mod)
    return mod


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
    api_main = _import_api_main()  # reads DATABASE_URL at import; startup() builds the pool

    with TestClient(api_main.app) as c:
        yield c


@pytest.fixture()
def source(client):
    """A Tier-A provider whose canonical domain covers example.com.

    The source is attested as reviewed because machine collection now requires a
    recorded terms-of-service decision (WP01 slice 10).
    """
    res = client.post("/sources", json={
        "provider": "Acme Domains",
        "canonical_domain": "example.com",
        "category": "domains",
        "adapter": "manual",
        "trust_tier": "A_provider_owned",
    })
    assert res.status_code == 201, res.text
    source_id = res.json()["id"]
    review = client.post(f"/sources/{source_id}/tos-review", json={
        "reference": "https://example.com/terms", "reviewer": "pytest",
    })
    assert review.status_code == 200, review.text
    return source_id


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
        "source_id": source,
        "official": True,
        "excerpt": "Twelve months free, then standard renewal. New accounts only.",
        "captured_content": "Twelve months free, then standard renewal. New accounts only.",
        "supported_fields": ["value", "eligibility"],
        **_procured(
            "https://example.com/terms/free-domain",
            "Twelve months free, then standard renewal. New accounts only.",
        ),
    })
    assert ev.status_code == 201, ev.text
    assert ev.json()["domain_ok"] is True and ev.json()["created"] is True

    # extraction: every field maps to its evidence URL (complete = True)
    ext = client.post(f"/offers/{offer_id}/extraction", json={
        "fields": {
            "value": {"value": "Twelve months free", "evidence_id": ev.json()["id"],
                      "excerpt": "Twelve months free, then standard renewal.",
                      "evidence_url": "https://example.com/terms/free-domain"},
            "eligibility": {"value": "New accounts", "evidence_id": ev.json()["id"],
                            "excerpt": "New accounts only.",
                            "evidence_url": "https://example.com/terms/free-domain"},
        },
        "complete": True,
        "model": "pytest",
        "coverage": _coverage(ev.json()["id"]),
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


# ------------------------------------------------- v0.16: identity + approval integrity

import secrets

import fastapi

import api_hardening
from automation_api import router as _automation_router
from captures_api import router as _captures_router
from offers_api import router as _offers_router
from renders_api import router as _renders_router
from schedules_api import router as _schedules_router
from health_api import router as _health_router
from locks_api import router as _locks_router
from settings_api import router as _settings_router
from analytics_api import router as _analytics_router
from schedules_state import script_version_hash


def test_script_hash_reaches_renders_roundtrip(client):
    """§17 chain: script markdown → version_hash (list_scripts) → render row →
    GET /renders — the exact values the publishing worker compares."""
    res = client.post("/offers", json={
        "provider": "Hash Chain Co", "category": "domains", "offer_type": "coupon",
    })
    offer_id = res.json()["id"]
    markdown = "# claim guide v1\n\nstep one cites evidence.\n"
    _run("INSERT INTO offer_scripts (offer_id, version, markdown) VALUES ($1, 1, $2)",
         __import__("uuid").UUID(offer_id), markdown)

    scripts = client.get(f"/offers/{offer_id}/scripts").json()
    assert scripts[0]["version_hash"] == script_version_hash(markdown)

    _run(
        """
        INSERT INTO renders (offer_id, preset, width, height, video_path,
                             script_version, script_version_hash)
        VALUES ($1, 'landscape', 1920, 1080, 'projects/x/r.mp4', 1, $2)
        """,
        __import__("uuid").UUID(offer_id), scripts[0]["version_hash"],
    )
    renders = client.get("/renders", params={"offer_id": offer_id}).json()
    assert renders[0]["script_version_hash"] == scripts[0]["version_hash"] == script_version_hash(markdown)


AUTH_TOKEN = "rtok-" + secrets.token_urlsafe(24)
REVIEWER = "Kashi Test"


@pytest.fixture(scope="session")
def auth_client(client):
    """Same global pool, but with full auth: shared service token + reviewer
    token resolution against the REAL reviewers table."""
    _run("INSERT INTO reviewers (name, token_hash) VALUES ($1, $2) "
         "ON CONFLICT (name) DO UPDATE SET token_hash = EXCLUDED.token_hash, active = TRUE",
         REVIEWER, api_hardening.token_hash(AUTH_TOKEN))

    app2 = fastapi.FastAPI()

    @app2.on_event("startup")
    async def _own_pool():
        # app2's TestClient runs its own event loop; the main pool belongs to
        # the `client` fixture's loop and asyncpg pools are loop-bound.
        import db
        await db.init(DSN)

    @app2.on_event("shutdown")
    async def _drop_own_pool():
        import db
        await db.close()

    for r in (_offers_router, _schedules_router, _renders_router, _captures_router,
              _settings_router, _analytics_router, _health_router, _locks_router,
              _automation_router):
        app2.include_router(r)
    api_hardening.register(app2, token="svc-token", db_url=DSN)
    app2.include_router(api_hardening.router)
    with TestClient(app2) as c:
        yield c


def _run(sql, *args):
    async def go():
        conn = await asyncpg.connect(DSN)
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()
    return asyncio.run(go())


# --------------------------------------- WP01: literal snapshot verification

SNAPSHOT_TEXT = "Use promo code SAVE2026 for verified students only."
SNAPSHOT_URL = "https://example.com/wp01-terms"


def _procured(url, text, *, fetched_at=None, redirects=(), robots=None):
    """Raw bytes + fetch provenance, as the acquisition worker sends them."""
    raw = text.encode("utf-8")
    fetched = fetched_at or datetime.now(timezone.utc)
    host = url_split(url).hostname
    if robots is None:
        robots = {
            "robots_url": f"https://{host}/robots.txt",
            "checked_at": (fetched - timedelta(minutes=1)).isoformat(),
            "allowed": True,
            "status": 200,
        }
    provenance = {
        "requested_url": url,
        "final_url": url,
        "http_status": 200,
        "content_type": "text/html",
        "fetched_at": fetched.isoformat(),
        "redirects": list(redirects),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "parser_version": "page_watch/1",
        "fetch_identity": "integration-test",
        "encoding": "utf-8",
        "robots": robots,
    }
    key = os.environ.get("MTK_FETCH_SIGNING_KEY", "").strip()
    if key:
        provenance["signature"] = sign_provenance(provenance, key)
    return {
        "raw_content_b64": base64.b64encode(raw).decode("ascii"),
        "provenance": provenance,
    }


def _coverage(*evidence_ids, sections=1):
    """A coverage record for short (single-section) snapshots."""
    return {
        "version": "paragraph-groups/1", "sections_total": sections,
        "max_section_chars": 6000,
        "evidence_ids": [str(item) for item in evidence_ids],
    }


def _attest(client, source_id):
    """Record the terms-of-service review machine collection now requires."""
    response = client.post(f"/sources/{source_id}/tos-review", json={
        "reference": "https://example.com/terms", "reviewer": "pytest",
    })
    assert response.status_code == 200, response.text
    return response.json()


def _verification_fixture(client):
    import uuid
    provider = f"WP01 {uuid.uuid4()}"
    source = client.post("/sources", json={
        "provider": provider, "canonical_domain": "example.com", "category": "student_programs",
        "adapter": "manual", "trust_tier": "A_provider_owned",
    })
    assert source.status_code == 201, source.text
    _attest(client, source.json()["id"])
    offer = client.post("/offers", json={
        "provider": provider, "category": "student_programs", "offer_type": "coupon",
    })
    assert offer.status_code == 201, offer.text
    oid = offer.json()["id"]
    response = client.post(f"/offers/{oid}/transition", json={"to": "evidence_needed"})
    assert response.status_code == 200, response.text
    payload = {
        "url": SNAPSHOT_URL, "source_id": source.json()["id"],
        "official": True, "captured_content": SNAPSHOT_TEXT,
        **_procured(SNAPSHOT_URL, SNAPSHOT_TEXT),
    }
    evidence = client.post(f"/offers/{oid}/evidence", json=payload)
    assert evidence.status_code == 201, evidence.text
    fields = {name: {
        "value": value, "excerpt": SNAPSHOT_TEXT, "evidence_url": SNAPSHOT_URL,
        "evidence_id": evidence.json()["id"], "confidence": 0.8,
    } for name, value in (("promo_code", "SAVE2026"), ("eligibility", "students"))}
    return oid, source.json()["id"], evidence.json()["id"], fields, payload


def _verified_offer(client):
    """A fresh verified offer: complete fact pack, recheck deadline set."""
    oid, _, eid, fields, _ = _verification_fixture(client)
    response = client.post(f"/offers/{oid}/extraction", json={
        "fields": fields, "coverage": _coverage(eid),
    })
    assert response.status_code == 201, response.text
    promoted = client.post(f"/offers/{oid}/transition", json={"to": "verified"})
    assert promoted.status_code == 200, promoted.text
    return oid


def test_capture_refuses_expired_or_overdue_offers(client):
    """Recording footage acts on the claims; stale claims block it (slice 12)."""
    import uuid
    oid = _verified_offer(client)
    fresh = client.post(f"/offers/{oid}/captures",
                        json={"step_log": [{"action": "open terms"}]})
    assert fresh.status_code == 201, fresh.text

    _run("UPDATE offers SET recheck_at = now() - interval '1 hour' "
         "WHERE id = $1", uuid.UUID(oid))
    overdue = client.post(f"/offers/{oid}/captures",
                          json={"step_log": [{"action": "open terms"}]})
    assert overdue.status_code == 409, overdue.text
    assert "recheck" in overdue.json()["detail"]
    assert "§11 freshness" in overdue.json()["detail"]

    _run("UPDATE offers SET recheck_at = now() + interval '1 day', "
         "expires_at = now() - interval '1 hour' WHERE id = $1", uuid.UUID(oid))
    expired = client.post(f"/offers/{oid}/captures",
                          json={"step_log": [{"action": "open terms"}]})
    assert expired.status_code == 409, expired.text
    assert "expired" in expired.json()["detail"]
    assert "§11 freshness" in expired.json()["detail"]


def test_resume_refuses_an_offer_whose_freshness_lapsed(client):
    import uuid
    oid = _verified_offer(client)
    sid = _run(
        "INSERT INTO schedules (offer_id, platform, state, local_time, privacy, "
        "idempotency_key) VALUES ($1, 'youtube', 'paused', now(), 'private', $2) "
        "RETURNING id",
        uuid.UUID(oid), f"fresh-{uuid.uuid4()}",
    )[0]["id"]

    _run("UPDATE offers SET recheck_at = now() - interval '1 hour' "
         "WHERE id = $1", uuid.UUID(oid))
    blocked = client.post(f"/schedules/{sid}/resume", params={"reviewer": "pytest"})
    assert blocked.status_code == 409, blocked.text
    assert "recheck" in blocked.json()["detail"]
    assert "§11 freshness" in blocked.json()["detail"]

    _run("UPDATE offers SET recheck_at = now() + interval '1 day' "
         "WHERE id = $1", uuid.UUID(oid))
    resumed = client.post(f"/schedules/{sid}/resume", params={"reviewer": "pytest"})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["state"] == "scheduled"


def test_recheck_deadline_is_capped_by_the_offer_expiry(client):
    """An offer expiring in hours must not get a two-day recheck deadline."""
    import uuid
    oid, _, eid, fields, _ = _verification_fixture(client)
    expiry = datetime.now(timezone.utc) + timedelta(hours=6)
    patched = client.patch(f"/offers/{oid}", json={"expires_at": expiry.isoformat()})
    assert patched.status_code == 200, patched.text
    assert client.post(f"/offers/{oid}/extraction", json={
        "fields": fields, "coverage": _coverage(eid),
    }).status_code == 201
    promoted = client.post(f"/offers/{oid}/transition", json={"to": "verified"})
    assert promoted.status_code == 200, promoted.text

    row = _run("SELECT recheck_at, expires_at FROM offers WHERE id = $1",
               uuid.UUID(oid))[0]
    assert row["recheck_at"] is not None
    assert row["recheck_at"] <= row["expires_at"]
    assert row["recheck_at"] > datetime.now(timezone.utc)


def test_recheck_deadline_keeps_the_policy_for_a_distant_expiry(client):
    import uuid
    oid, _, eid, fields, _ = _verification_fixture(client)
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    assert client.patch(f"/offers/{oid}", json={
        "expires_at": expiry.isoformat(),
    }).status_code == 200
    assert client.post(f"/offers/{oid}/extraction", json={
        "fields": fields, "coverage": _coverage(eid),
    }).status_code == 201
    assert client.post(f"/offers/{oid}/transition",
                       json={"to": "verified"}).status_code == 200
    row = _run("SELECT recheck_at FROM offers WHERE id = $1", uuid.UUID(oid))[0]
    now = datetime.now(timezone.utc)
    assert now + timedelta(days=1) < row["recheck_at"] < now + timedelta(days=3)


def test_coverage_must_include_claim_free_pages_from_the_run(client):
    """A skipped page with no claims cannot be omitted from the run's coverage."""
    import uuid
    oid, source_id, eid, fields, _ = _verification_fixture(client)
    other_url = f"https://example.com/wp01-notes-{uuid.uuid4().hex}"
    other_text = "General programme terms apply. Students must verify enrolment."
    other = client.post(f"/offers/{oid}/evidence", json={
        "url": other_url, "source_id": source_id, "official": True,
        "captured_content": other_text, **_procured(other_url, other_text),
    })
    assert other.status_code == 201, other.text

    partial = client.post(f"/offers/{oid}/extraction", json={
        "fields": fields, "coverage": _coverage(eid),
    })
    assert partial.status_code == 201, partial.text
    blocked = client.post(f"/offers/{oid}/transition", json={"to": "verified"})
    assert blocked.status_code == 422, blocked.text
    assert "does not include" in blocked.json()["detail"]

    full = client.post(f"/offers/{oid}/extraction", json={
        "fields": fields, "coverage": _coverage(eid, other.json()["id"], sections=2),
    })
    assert full.status_code == 201, full.text
    promoted = client.post(f"/offers/{oid}/transition", json={"to": "verified"})
    assert promoted.status_code == 200, promoted.text


def test_snapshot_and_extraction_roundtrip_is_server_derived(client):
    import hashlib
    import uuid
    oid, _, eid, fields, payload = _verification_fixture(client)
    duplicate = client.post(f"/offers/{oid}/evidence", json=payload)
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["id"] == eid and duplicate.json()["duplicate"] is True
    row = _run("SELECT captured_content, content_hash FROM evidence WHERE id = $1", uuid.UUID(eid))[0]
    assert row["captured_content"] == SNAPSHOT_TEXT
    assert row["content_hash"] == hashlib.sha256(SNAPSHOT_TEXT.encode()).hexdigest()
    # False or omitted caller hints cannot override the server's calculation.
    response = client.post(f"/offers/{oid}/extraction", json={
        "fields": fields, "complete": False, "coverage": _coverage(eid),
    })
    assert response.status_code == 201, response.text
    assert response.json()["complete"] is True
    assert response.json()["validation_errors"] == []
    verified = client.post(f"/offers/{oid}/transition", json={"to": "verified"})
    assert verified.status_code == 200, verified.text
    # Text is retained privately, not added to the general workspace response.
    assert "captured_content" not in client.get(f"/offers/{oid}").json()["evidence"][0]


def _long_snapshot(client, offer_id, source_id, repeats=300):
    """A snapshot long enough to require more than one section."""
    import uuid
    text = "Conditions apply to students only. Use code SAVE2026 at checkout.\n\n" * repeats
    url = f"https://example.com/wp01-long-{uuid.uuid4().hex}"
    response = client.post(f"/offers/{offer_id}/evidence", json={
        "url": url, "source_id": source_id, "official": True,
        "captured_content": text, **_procured(url, text),
    })
    assert response.status_code == 201, response.text
    return text, response.json()["id"]


def test_extraction_coverage_is_recomputed_from_the_snapshot(client):
    from document_sections import split_sections
    oid, source_id, _, fields, _ = _verification_fixture(client)
    text, long_id = _long_snapshot(client, oid, source_id)
    expected = len(split_sections(text))
    assert expected > 1
    coverage = {
        "version": "paragraph-groups/1", "sections_total": expected,
        "max_section_chars": 6000, "evidence_ids": [long_id],
    }
    response = client.post(f"/offers/{oid}/extraction",
                           json={"fields": fields, "coverage": coverage})
    assert response.status_code == 201, response.text
    assert response.json()["coverage"]["sections_total"] == expected
    shown = client.get(f"/offers/{oid}").json()["extraction"]["coverage"]
    assert shown["version"] == "paragraph-groups/1"
    assert shown["sections_total"] == expected
    assert shown["evidence_ids"] == [long_id]


@pytest.mark.parametrize("override,needle", [
    ({"sections_total": 1}, "section count"),
    ({"version": "paragraph-groups/2"}, "coverage version"),
    ({"max_section_chars": 5999}, "max_section_chars"),
    ({"evidence_ids": ["00000000-0000-0000-0000-000000000000"]}, "outside this offer"),
])
def test_coverage_must_match_the_stored_snapshots(client, override, needle):
    oid, source_id, _, fields, _ = _verification_fixture(client)
    _, long_id = _long_snapshot(client, oid, source_id)
    coverage = {
        "version": "paragraph-groups/1", "sections_total": 2,
        "max_section_chars": 6000, "evidence_ids": [long_id],
    }
    coverage.update(override)
    response = client.post(f"/offers/{oid}/extraction",
                           json={"fields": fields, "coverage": coverage})
    assert response.status_code == 422, response.text
    assert needle in response.json()["detail"]


@pytest.mark.parametrize("case", ["empty", "conflicts", "foreign_id", "wrong_url", "quote", "value"])
def test_unearned_complete_never_promotes_on_real_database(client, case):
    import uuid
    oid, _, _, fields, _ = _verification_fixture(client)
    conflicts = []
    if case == "empty":
        fields = {}
    elif case == "conflicts":
        conflicts = [{"field": "eligibility", "reason": "official terms disagree"}]
    elif case == "foreign_id":
        other = _verification_fixture(client)
        fields["promo_code"]["evidence_id"] = other[2]
    elif case == "wrong_url":
        fields["promo_code"]["evidence_url"] = "https://example.com/unrelated"
    elif case == "quote":
        fields["promo_code"]["excerpt"] = "Use promo code SAVE2026 for everyone forever."
    elif case == "value":
        fields["promo_code"]["value"] = "INVENTED"
    response = client.post(f"/offers/{oid}/extraction", json={
        "fields": fields, "complete": True, "conflicts": conflicts,
    })
    assert response.status_code == 201, response.text
    assert response.json()["complete"] is False
    stored = _run("SELECT complete FROM extractions WHERE id = $1", uuid.UUID(response.json()["id"]))[0]
    assert stored["complete"] is False
    result = client.post(f"/offers/{oid}/transition", json={"to": "verified"})
    assert result.status_code == 422, result.text
    assert client.get(f"/offers/{oid}").json()["state"] == "evidence_needed"


@pytest.mark.parametrize("change", ["disabled", "downgraded", "renamed_provider"])
def test_current_source_authorization_is_rechecked(client, change):
    import uuid
    oid, sid, _, fields, payload = _verification_fixture(client)
    assert client.post(f"/offers/{oid}/extraction", json={"fields": fields}).json()["complete"] is True
    sql = {
        "disabled": "UPDATE sources SET enabled = FALSE WHERE id = $1",
        "downgraded": "UPDATE sources SET trust_tier = 'B_discovery_lead' WHERE id = $1",
        "renamed_provider": "UPDATE sources SET provider = 'Different owner' WHERE id = $1",
    }[change]
    _run(sql, uuid.UUID(sid))
    assert client.post(f"/offers/{oid}/transition", json={"to": "verified"}).status_code == 422
    assert client.post(f"/offers/{oid}/evidence", json=payload).status_code == 422


@pytest.mark.parametrize("valid_replacement", [False, True])
def test_new_extraction_revokes_verification_and_pauses_posts(client, valid_replacement):
    import uuid
    oid, _, eid, fields, _ = _verification_fixture(client)
    assert client.post(f"/offers/{oid}/extraction", json={
        "fields": fields, "coverage": _coverage(eid),
    }).json()["complete"] is True
    assert client.post(f"/offers/{oid}/transition", json={"to": "verified"}).status_code == 200
    sid = _run(
        "INSERT INTO schedules (offer_id, platform, state, local_time, privacy, idempotency_key) "
        "VALUES ($1, 'youtube', 'scheduled', now(), 'private', $2) RETURNING id",
        uuid.UUID(oid), f"wp01-{uuid.uuid4()}",
    )[0]["id"]
    response = client.post(f"/offers/{oid}/extraction", json={
        "fields": fields if valid_replacement else {}, "complete": True,
        "coverage": _coverage(eid),
    })
    assert response.status_code == 201 and response.json()["complete"] is valid_replacement
    assert client.get(f"/offers/{oid}").json()["state"] == "evidence_needed"
    assert _run("SELECT state::text AS state FROM schedules WHERE id = $1", sid)[0]["state"] == "paused"


def test_legacy_complete_flag_is_revalidated_not_grandfathered(client):
    import uuid
    oid, _, _, _, _ = _verification_fixture(client)
    _run("INSERT INTO extractions (offer_id, fields, complete) VALUES ($1, '{}', TRUE)", uuid.UUID(oid))
    assert client.post(f"/offers/{oid}/transition", json={"to": "verified"}).status_code == 422


def test_legacy_audit_reports_a_verified_offer_that_would_fail_today(client):
    import uuid
    good = _verified_offer(client)
    bad = _verified_offer(client)
    _run("UPDATE extractions SET coverage = NULL WHERE offer_id = $1", uuid.UUID(bad))
    _run(
        "INSERT INTO schedules (offer_id, platform, state, local_time, privacy, "
        "idempotency_key) VALUES ($1, 'youtube', 'scheduled', now(), 'private', $2)",
        uuid.UUID(bad), f"audit-{uuid.uuid4()}",
    )

    report = client.get("/offers/audit/verified").json()
    failed = {row["id"]: row for row in report["offers"]}
    assert bad in failed
    assert good not in failed
    assert any("coverage" in problem for problem in failed[bad]["problems"])
    assert failed[bad]["impact"]["schedules"] == 1
    assert failed[bad]["impact"]["scheduled"] == 1
    assert report["checked"] >= 2
    assert report["failed"] == len(report["offers"])
    assert report["requirements"]["extraction_coverage"] is True
    # Read-only: the audit never demotes on its own.
    assert client.get(f"/offers/{bad}").json()["state"] == "verified"
    assert _run("SELECT state::text AS state FROM schedules WHERE offer_id = $1",
                uuid.UUID(bad))[0]["state"] == "scheduled"


def test_legacy_audit_names_a_verified_offer_with_no_extraction(client):
    import uuid
    offer = client.post("/offers", json={
        "provider": "Legacy Audit Co", "category": "domains", "offer_type": "coupon",
    })
    oid = offer.json()["id"]
    _run("UPDATE offers SET state = 'verified' WHERE id = $1", uuid.UUID(oid))

    report = client.get("/offers/audit/verified").json()
    row = next(item for item in report["offers"] if item["id"] == oid)
    assert row["problems"] == [
        "requires structured extraction with official snapshot evidence"
    ]


def test_hash_only_legacy_snapshot_cannot_support_new_verification(client):
    import hashlib
    import uuid
    oid, _, _, fields, _ = _verification_fixture(client)
    eid = _run(
        "INSERT INTO evidence (offer_id, url, content_hash, official, domain_ok) "
        "VALUES ($1,$2,$3,TRUE,TRUE) RETURNING id",
        uuid.UUID(oid), SNAPSHOT_URL, hashlib.sha256(SNAPSHOT_TEXT.encode()).hexdigest(),
    )[0]["id"]
    for field in fields.values():
        field["evidence_id"] = str(eid)
    response = client.post(f"/offers/{oid}/extraction", json={"fields": fields, "complete": True})
    assert response.status_code == 201 and response.json()["complete"] is False
    assert any("recapture" in error for error in response.json()["validation_errors"])
    assert client.post(f"/offers/{oid}/transition", json={"to": "verified"}).status_code == 422


def test_evidence_identity_includes_url_and_authority(client):
    oid, _, eid, _, payload = _verification_fixture(client)
    other_url = SNAPSHOT_URL + "/other"
    different_url = client.post(f"/offers/{oid}/evidence", json={
        **payload, "url": other_url, **_procured(other_url, SNAPSHOT_TEXT),
    })
    assert different_url.status_code == 201 and different_url.json()["id"] != eid
    unofficial = client.post(f"/offers/{oid}/evidence", json={**payload, "official": False})
    assert unofficial.status_code == 201 and unofficial.json()["id"] != eid
    # Equal bytes do not silently inherit a different evidence row's authority.
    again = client.post(f"/offers/{oid}/evidence", json=payload)
    assert again.json()["id"] == eid and again.json()["created"] is False


def test_raw_bytes_and_provenance_are_preserved(client):
    """The exact bytes the provider served are stored, hashed and auditable."""
    import uuid
    oid, _, eid, _, _ = _verification_fixture(client)
    row = _run(
        "SELECT raw_content, raw_hash, requested_url, fetch_status, fetched_at, "
        "parser_version, fetch_identity, fetch_redirects::text AS fetch_redirects, "
        "robots_url, robots_checked_at, robots_allowed, robots_status, fetch_signature "
        "FROM evidence WHERE id = $1",
        uuid.UUID(eid),
    )[0]
    raw = bytes(row["raw_content"])
    assert raw == SNAPSHOT_TEXT.encode("utf-8")
    assert row["raw_hash"] == hashlib.sha256(raw).hexdigest()
    assert row["requested_url"] == SNAPSHOT_URL
    assert row["fetch_status"] == 200
    assert row["fetched_at"] is not None
    assert row["parser_version"] == "page_watch/1"
    assert row["fetch_identity"] == "integration-test"
    assert json.loads(row["fetch_redirects"]) == []
    assert row["robots_url"] == "https://example.com/robots.txt"
    assert row["robots_checked_at"] is not None
    assert row["robots_allowed"] is True
    assert row["robots_status"] == 200
    assert row["fetch_signature"] is not None and len(row["fetch_signature"]) == 64

    shown = client.get(f"/offers/{oid}").json()["evidence"][0]
    assert shown["raw_preserved"] is True
    assert shown["raw_hash"] == row["raw_hash"]
    assert shown["parser_version"] == "page_watch/1"
    assert shown["robots_allowed"] is True
    assert shown["fetch_signature"] == row["fetch_signature"]
    # Raw bytes stay out of the general workspace response.
    assert "raw_content" not in shown


def test_tampered_raw_hash_is_rejected(client):
    oid, _, _, _, payload = _verification_fixture(client)
    tampered = {**payload, "provenance": {**payload["provenance"], "raw_sha256": "0" * 64}}
    response = client.post(f"/offers/{oid}/evidence", json=tampered)
    assert response.status_code == 422
    assert "hash does not match" in response.json()["detail"]


def test_off_provider_redirect_chain_is_rejected(client):
    oid, _, _, _, payload = _verification_fixture(client)
    poisoned = {
        **payload,
        "provenance": {
            **payload["provenance"],
            "redirects": ["https://evil.test/promo", payload["provenance"]["final_url"]],
        },
    }
    response = client.post(f"/offers/{oid}/evidence", json=poisoned)
    assert response.status_code == 422
    assert "evil.test" in response.json()["detail"]


def test_evidence_url_must_be_the_final_fetched_url(client):
    oid, _, _, _, payload = _verification_fixture(client)
    mismatched = {**payload, "url": SNAPSHOT_URL + "/elsewhere"}
    response = client.post(f"/offers/{oid}/evidence", json=mismatched)
    assert response.status_code == 422
    assert "final fetched URL" in response.json()["detail"]


def test_evidence_without_a_robots_decision_is_rejected(client):
    """Permission is part of the provenance, not an optional extra (slice 6)."""
    import uuid
    oid, _, _, _, payload = _verification_fixture(client)
    url = "https://example.com/wp01-no-robots-" + uuid.uuid4().hex
    broken = {**payload, "url": url, **_procured(url, SNAPSHOT_TEXT)}
    broken["provenance"] = {
        key: value for key, value in broken["provenance"].items() if key != "robots"
    }
    response = client.post(f"/offers/{oid}/evidence", json=broken)
    assert response.status_code == 422
    assert "robots.txt" in response.json()["detail"]


def test_evidence_from_a_disallowing_robots_policy_is_rejected(client):
    import uuid
    oid, _, _, _, payload = _verification_fixture(client)
    url = "https://example.com/wp01-denied-" + uuid.uuid4().hex
    robots = {
        "robots_url": "https://example.com/robots.txt",
        "checked_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "allowed": False,
        "status": 403,
    }
    broken = {**payload, "url": url, **_procured(url, SNAPSHOT_TEXT, robots=robots)}
    response = client.post(f"/offers/{oid}/evidence", json=broken)
    assert response.status_code == 422
    assert "did not permit" in response.json()["detail"]


def test_robots_decision_must_come_from_the_fetched_host(client):
    import uuid
    oid, _, _, _, payload = _verification_fixture(client)
    url = "https://example.com/wp01-robots-host-" + uuid.uuid4().hex
    robots = {
        "robots_url": "https://elsewhere.test/robots.txt",
        "checked_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "allowed": True,
        "status": 200,
    }
    broken = {**payload, "url": url, **_procured(url, SNAPSHOT_TEXT, robots=robots)}
    response = client.post(f"/offers/{oid}/evidence", json=broken)
    assert response.status_code == 422
    assert "fetched host" in response.json()["detail"]


def test_unsigned_provenance_is_rejected(client):
    """WP01 slice 7: an unsigned record only names its author, it does not prove it."""
    import uuid
    oid, _, _, _, payload = _verification_fixture(client)
    url = "https://example.com/wp01-unsigned-" + uuid.uuid4().hex
    broken = {**payload, "url": url, **_procured(url, SNAPSHOT_TEXT)}
    broken["provenance"] = {
        key: value for key, value in broken["provenance"].items() if key != "signature"
    }
    response = client.post(f"/offers/{oid}/evidence", json=broken)
    assert response.status_code == 422
    assert "not signed" in response.json()["detail"]


def test_tampered_signature_is_rejected(client):
    import uuid
    oid, _, _, _, payload = _verification_fixture(client)
    url = "https://example.com/wp01-tampered-signature-" + uuid.uuid4().hex
    broken = {**payload, "url": url, **_procured(url, SNAPSHOT_TEXT)}
    broken["provenance"] = {**broken["provenance"], "signature": "0" * 64}
    response = client.post(f"/offers/{oid}/evidence", json=broken)
    assert response.status_code == 422
    assert "signature does not match" in response.json()["detail"]


def test_signing_must_be_configured_server_side(client, monkeypatch):
    """A missing key is a deployment error, not permission to accept a claim."""
    import uuid
    oid, _, _, _, payload = _verification_fixture(client)
    monkeypatch.setenv("MTK_FETCH_SIGNING_KEY", "")
    url = "https://example.com/wp01-no-key-" + uuid.uuid4().hex
    broken = {**payload, "url": url, **_procured(url, SNAPSHOT_TEXT)}
    response = client.post(f"/offers/{oid}/evidence", json=broken)
    assert response.status_code == 503
    assert "MTK_FETCH_SIGNING_KEY" in response.json()["detail"]


def test_signature_opt_out_accepts_an_unsigned_legacy_record(client, monkeypatch):
    """The documented migration escape hatch, recorded as absent, not as valid."""
    import uuid
    monkeypatch.setenv("MTK_REQUIRE_FETCH_SIGNATURE", "0")
    oid, _, _, _, payload = _verification_fixture(client)
    url = "https://example.com/wp01-unsigned-ok-" + uuid.uuid4().hex
    unsigned = {**payload, "url": url, **_procured(url, SNAPSHOT_TEXT)}
    unsigned["provenance"] = {
        key: value for key, value in unsigned["provenance"].items()
        if key != "signature"
    }
    response = client.post(f"/offers/{oid}/evidence", json=unsigned)
    assert response.status_code == 201, response.text
    assert response.json()["provenance"]["fetch_signature"] is None


def test_future_fetch_time_is_rejected(client):
    oid, _, _, _, payload = _verification_fixture(client)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    response = client.post(f"/offers/{oid}/evidence", json={
        **payload, **_procured(SNAPSHOT_URL, SNAPSHOT_TEXT, fetched_at=future),
    })
    assert response.status_code == 422
    assert "future" in response.json()["detail"]


def test_verification_requires_raw_provenance_on_real_database(client):
    """Text-only evidence can be stored but can never earn verified."""
    import uuid
    text = "Use promo code SAVE2026 for verified students only."
    provider = f"WP01P {uuid.uuid4()}"
    source = client.post("/sources", json={
        "provider": provider, "canonical_domain": "example.com",
        "category": "student_programs", "adapter": "manual",
        "trust_tier": "A_provider_owned",
    })
    offer = client.post("/offers", json={
        "provider": provider, "category": "student_programs", "offer_type": "coupon",
    })
    oid = offer.json()["id"]
    client.post(f"/offers/{oid}/transition", json={"to": "evidence_needed"})
    evidence = client.post(f"/offers/{oid}/evidence", json={
        "url": SNAPSHOT_URL, "source_id": source.json()["id"],
        "official": True, "captured_content": text,   # no raw bytes, no provenance
    })
    assert evidence.status_code == 201, evidence.text
    assert evidence.json()["raw_preserved"] is False
    eid = evidence.json()["id"]
    fields = {name: {
        "value": value, "excerpt": text, "evidence_url": SNAPSHOT_URL,
        "evidence_id": eid, "confidence": 0.8,
    } for name, value in (("promo_code", "SAVE2026"), ("eligibility", "students"))}
    extracted = client.post(f"/offers/{oid}/extraction", json={"fields": fields})
    assert extracted.status_code == 201
    assert extracted.json()["complete"] is True  # the terms are satisfied ...
    blocked = client.post(f"/offers/{oid}/transition", json={"to": "verified"})
    assert blocked.status_code == 422            # ... but the bytes are not proven
    assert "raw page bytes" in blocked.json()["detail"]
    assert "robots.txt" in blocked.json()["detail"]


def test_raw_snapshot_database_check_rejects_alteration(client):
    import uuid
    oid, _, eid, _, _ = _verification_fixture(client)
    with pytest.raises(asyncpg.CheckViolationError):
        _run(
            "UPDATE evidence SET raw_content = $2 WHERE id = $1",
            uuid.UUID(eid), b"tampered bytes",
        )


def test_simultaneous_proposal_and_promotion_cannot_leave_verified(client):
    from concurrent.futures import ThreadPoolExecutor
    oid, _, eid, fields, _ = _verification_fixture(client)
    assert client.post(f"/offers/{oid}/extraction", json={
        "fields": fields, "coverage": _coverage(eid),
    }).json()["complete"] is True
    with ThreadPoolExecutor(max_workers=2) as executor:
        promote = executor.submit(client.post, f"/offers/{oid}/transition", json={"to": "verified"})
        replace = executor.submit(client.post, f"/offers/{oid}/extraction", json={"fields": {}})
        assert promote.result().status_code in (200, 422)
        assert replace.result().status_code == 201
    assert client.get(f"/offers/{oid}").json()["state"] == "evidence_needed"


def test_snapshot_migration_preserves_legacy_and_checks_new_text(client):
    """Upgrade real 001..011 tables in a new rollback-only schema, not user data."""
    import hashlib
    import uuid

    async def check():
        conn = await asyncpg.connect(DSN)
        tx = conn.transaction()
        await tx.start()
        try:
            schema = "wp01_upgrade_" + uuid.uuid4().hex
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            paths = db_migrate.migration_files()
            for path in paths[:11]:
                await conn.execute(path.read_text(encoding="utf-8"))
            oid = await conn.fetchval(
                "INSERT INTO offers (title, provider, category, offer_type) "
                "VALUES ('legacy', 'Legacy', 'domains', 'coupon') RETURNING id")
            digest = hashlib.sha256(SNAPSHOT_TEXT.encode()).hexdigest()
            eid = await conn.fetchval(
                "INSERT INTO evidence (offer_id, url, content_hash) VALUES ($1, $2, $3) RETURNING id",
                oid, SNAPSHOT_URL, digest)
            await conn.execute(paths[11].read_text(encoding="utf-8"))
            assert await conn.fetchval("SELECT captured_content FROM evidence WHERE id = $1", eid) is None
            await conn.execute(
                "INSERT INTO evidence (offer_id, url, content_hash, captured_content) VALUES ($1,$2,$3,$4)",
                oid, SNAPSHOT_URL, digest, SNAPSHOT_TEXT)
            with pytest.raises(asyncpg.CheckViolationError):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO evidence (offer_id, url, content_hash, captured_content) VALUES ($1,$2,$3,$4)",
                        oid, SNAPSHOT_URL + "/bad", "0" * 64, SNAPSHOT_TEXT)
        finally:
            await tx.rollback()
            await conn.close()
    asyncio.run(check())


def test_fetch_provenance_migration_preserves_legacy_and_checks_raw_hash(client):
    """Upgrade 001..013 in a rollback-only schema; legacy rows get no provenance."""
    import hashlib
    import uuid

    async def check():
        conn = await asyncpg.connect(DSN)
        tx = conn.transaction()
        await tx.start()
        try:
            schema = "wp01_fetch_" + uuid.uuid4().hex
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            paths = db_migrate.migration_files()
            for path in paths[:13]:
                await conn.execute(path.read_text(encoding="utf-8"))
            oid = await conn.fetchval(
                "INSERT INTO offers (title, provider, category, offer_type) "
                "VALUES ('legacy', 'Legacy', 'domains', 'coupon') RETURNING id")
            digest = hashlib.sha256(SNAPSHOT_TEXT.encode()).hexdigest()
            eid = await conn.fetchval(
                "INSERT INTO evidence (offer_id, url, content_hash) VALUES ($1,$2,$3) RETURNING id",
                oid, SNAPSHOT_URL, digest)
            await conn.execute(paths[13].read_text(encoding="utf-8"))
            row = await conn.fetchrow(
                "SELECT raw_content, raw_hash, requested_url FROM evidence WHERE id = $1", eid)
            assert row["raw_content"] is None and row["raw_hash"] is None
            assert row["requested_url"] is None
            raw = SNAPSHOT_TEXT.encode()
            await conn.execute(
                "INSERT INTO evidence (offer_id, url, content_hash, raw_content, raw_hash, "
                "requested_url, fetched_at, parser_version) "
                "VALUES ($1,$2,$3,$4,$5,$6, now(), 'page_watch/1')",
                oid, SNAPSHOT_URL + "/ok", digest, raw,
                hashlib.sha256(raw).hexdigest(), SNAPSHOT_URL)
            with pytest.raises(asyncpg.CheckViolationError):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO evidence (offer_id, url, content_hash, raw_content, raw_hash, "
                        "requested_url, fetched_at, parser_version) "
                        "VALUES ($1,$2,$3,$4,$5,$6, now(), 'page_watch/1')",
                        oid, SNAPSHOT_URL + "/bad", digest, raw, "0" * 64, SNAPSHOT_URL)
        finally:
            await tx.rollback()
            await conn.close()
    asyncio.run(check())


def test_robots_permission_migration_never_invents_permission(client):
    """Upgrade 014→015: legacy bytes keep no permission record; new rows need one."""
    import hashlib
    import uuid

    async def check():
        conn = await asyncpg.connect(DSN)
        tx = conn.transaction()
        await tx.start()
        try:
            schema = "wp01_robots_" + uuid.uuid4().hex
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            paths = db_migrate.migration_files()
            target = next(p for p in paths if p.name.startswith("015_"))
            for path in paths:
                if path.name < target.name:
                    await conn.execute(path.read_text(encoding="utf-8"))
            oid = await conn.fetchval(
                "INSERT INTO offers (title, provider, category, offer_type) "
                "VALUES ('legacy', 'Legacy', 'domains', 'coupon') RETURNING id")
            raw = SNAPSHOT_TEXT.encode()
            digest = hashlib.sha256(SNAPSHOT_TEXT.encode()).hexdigest()
            eid = await conn.fetchval(
                "INSERT INTO evidence (offer_id, url, content_hash, raw_content, raw_hash, "
                "requested_url, fetched_at, parser_version) "
                "VALUES ($1,$2,$3,$4,$5,$6, now(), 'page_watch/1') RETURNING id",
                oid, SNAPSHOT_URL, digest, raw,
                hashlib.sha256(raw).hexdigest(), SNAPSHOT_URL)
            await conn.execute(target.read_text(encoding="utf-8"))
            row = await conn.fetchrow(
                "SELECT robots_url, robots_checked_at, robots_allowed, robots_status "
                "FROM evidence WHERE id = $1", eid)
            assert row["robots_url"] is None and row["robots_checked_at"] is None
            assert row["robots_allowed"] is None and row["robots_status"] is None
            # New rows must carry a permitted decision alongside raw bytes.
            with pytest.raises(asyncpg.CheckViolationError):
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO evidence (offer_id, url, content_hash, raw_content, raw_hash, "
                        "requested_url, fetched_at, parser_version) "
                        "VALUES ($1,$2,$3,$4,$5,$6, now(), 'page_watch/1')",
                        oid, SNAPSHOT_URL + "/new", digest, raw,
                        hashlib.sha256(raw).hexdigest(), SNAPSHOT_URL)
            await conn.execute(
                "INSERT INTO evidence (offer_id, url, content_hash, raw_content, raw_hash, "
                "requested_url, fetched_at, parser_version, robots_url, robots_checked_at, "
                "robots_allowed, robots_status) "
                "VALUES ($1,$2,$3,$4,$5,$6, now(), 'page_watch/1', $7, now(), TRUE, 200)",
                oid, SNAPSHOT_URL + "/ok", digest, raw,
                hashlib.sha256(raw).hexdigest(), SNAPSHOT_URL,
                "https://example.com/robots.txt")
        finally:
            await tx.rollback()
            await conn.close()
    asyncio.run(check())


def test_fetch_signature_migration_keeps_legacy_rows_unsigned(client):
    """Upgrade 015→016: legacy machine rows keep NULL, and only hex is storable."""
    import hashlib
    import uuid

    async def check():
        conn = await asyncpg.connect(DSN)
        tx = conn.transaction()
        await tx.start()
        try:
            schema = "wp01_signature_" + uuid.uuid4().hex
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            paths = db_migrate.migration_files()
            target = next(p for p in paths if p.name.startswith("016_"))
            for path in paths:
                if path.name < target.name:
                    await conn.execute(path.read_text(encoding="utf-8"))
            oid = await conn.fetchval(
                "INSERT INTO offers (title, provider, category, offer_type) "
                "VALUES ('legacy', 'Legacy', 'domains', 'coupon') RETURNING id")
            raw = SNAPSHOT_TEXT.encode()
            eid = await conn.fetchval(
                "INSERT INTO evidence (offer_id, url, content_hash, raw_content, raw_hash, "
                "requested_url, fetched_at, parser_version, robots_url, robots_checked_at, "
                "robots_allowed, robots_status) "
                "VALUES ($1,$2,$3,$4,$5,$6, now(), 'page_watch/1', $7, now(), TRUE, 200) "
                "RETURNING id",
                oid, SNAPSHOT_URL, hashlib.sha256(SNAPSHOT_TEXT.encode()).hexdigest(),
                raw, hashlib.sha256(raw).hexdigest(), SNAPSHOT_URL,
                "https://example.com/robots.txt")
            await conn.execute(target.read_text(encoding="utf-8"))
            signature = await conn.fetchval(
                "SELECT fetch_signature FROM evidence WHERE id = $1", eid)
            assert signature is None  # nothing is invented for pre-016 rows
            with pytest.raises(asyncpg.CheckViolationError):
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE evidence SET fetch_signature = 'not-a-signature' WHERE id = $1",
                        eid)
            await conn.execute(
                "UPDATE evidence SET fetch_signature = $2 WHERE id = $1", eid, "b" * 64)
            assert await conn.fetchval(
                "SELECT fetch_signature FROM evidence WHERE id = $1", eid) == "b" * 64
        finally:
            await tx.rollback()
            await conn.close()
    asyncio.run(check())


def test_extraction_coverage_migration_keeps_legacy_rows_uncovered(client):
    """Upgrade 016→017: pre-sectioned proposals carry no coverage claim."""
    import json
    import uuid

    async def check():
        conn = await asyncpg.connect(DSN)
        tx = conn.transaction()
        await tx.start()
        try:
            schema = "wp01_coverage_" + uuid.uuid4().hex
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            paths = db_migrate.migration_files()
            target = next(p for p in paths if p.name.startswith("017_"))
            for path in paths:
                if path.name < target.name:
                    await conn.execute(path.read_text(encoding="utf-8"))
            oid = await conn.fetchval(
                "INSERT INTO offers (title, provider, category, offer_type) "
                "VALUES ('legacy', 'Legacy', 'domains', 'coupon') RETURNING id")
            eid = await conn.fetchval(
                "INSERT INTO extractions (offer_id, fields, conflicts, complete, model) "
                "VALUES ($1, '{}'::jsonb, '[]'::jsonb, FALSE, 'rules/0.1') RETURNING id",
                oid)
            await conn.execute(target.read_text(encoding="utf-8"))
            assert await conn.fetchval(
                "SELECT coverage FROM extractions WHERE id = $1", eid) is None
            await conn.execute(
                "UPDATE extractions SET coverage = $2::jsonb WHERE id = $1", eid,
                json.dumps({
                    "version": "paragraph-groups/1", "sections_total": 1,
                    "max_section_chars": 6000,
                    "evidence_ids": [],
                }))
            stored = json.loads(await conn.fetchval(
                "SELECT coverage FROM extractions WHERE id = $1", eid))
            assert stored["version"] == "paragraph-groups/1"
        finally:
            await tx.rollback()
            await conn.close()
    asyncio.run(check())


# ------------------------------ WP01 slice 2: offer-type fact pack + statuses

FACT_PACK_TEXT = (
    "Free trial for students. Use promo code SAVE2026. "
    "Valid until 31 December 2026. "
    "The subscription renews automatically at $19 per month."
)


def _typed_fixture(client, offer_type, text=FACT_PACK_TEXT):
    """An offer with one official snapshot carrying the typed claims."""
    import uuid
    provider = f"WP01T {uuid.uuid4()}"
    source = client.post("/sources", json={
        "provider": provider, "canonical_domain": "example.com",
        "category": "student_programs", "adapter": "manual",
        "trust_tier": "A_provider_owned",
    })
    assert source.status_code == 201, source.text
    _attest(client, source.json()["id"])
    offer = client.post("/offers", json={
        "provider": provider, "category": "student_programs", "offer_type": offer_type,
    })
    assert offer.status_code == 201, offer.text
    oid = offer.json()["id"]
    assert client.post(f"/offers/{oid}/transition", json={"to": "evidence_needed"}).status_code == 200
    url = "https://example.com/typed-terms"
    evidence = client.post(f"/offers/{oid}/evidence", json={
        "url": url, "source_id": source.json()["id"],
        "official": True, "captured_content": text,
        **_procured(url, text),
    })
    assert evidence.status_code == 201, evidence.text
    eid = evidence.json()["id"]

    def field(value, **extra):
        return {
            "value": value, "excerpt": text, "evidence_url": url,
            "evidence_id": eid, "confidence": 0.8, **extra,
        }

    field.evidence_id = eid
    return oid, field


def _new_source(client, provider):
    response = client.post("/sources", json={
        "provider": provider, "canonical_domain": "example.com",
        "category": "student_programs", "adapter": "manual",
        "trust_tier": "A_provider_owned",
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _new_offer(client, provider):
    offer = client.post("/offers", json={
        "provider": provider, "category": "student_programs", "offer_type": "coupon",
    })
    assert offer.status_code == 201, offer.text
    offer_id = offer.json()["id"]
    assert client.post(f"/offers/{offer_id}/transition",
                       json={"to": "evidence_needed"}).status_code == 200
    return offer_id


def test_machine_evidence_requires_a_tos_attested_source(client):
    import uuid
    provider = f"WP01TOS {uuid.uuid4()}"
    source_id = _new_source(client, provider)
    offer_id = _new_offer(client, provider)
    url = "https://example.com/tos-terms"
    payload = {
        "url": url, "source_id": source_id, "official": True,
        "captured_content": SNAPSHOT_TEXT,
        **_procured(url, SNAPSHOT_TEXT),
    }
    blocked = client.post(f"/offers/{offer_id}/evidence", json=payload)
    assert blocked.status_code == 422, blocked.text
    assert "terms-of-service review" in blocked.json()["detail"]

    review = client.post(f"/sources/{source_id}/tos-review", json={
        "reference": "provider terms v3", "reviewer": "pytest",
    })
    assert review.status_code == 200, review.text
    assert review.json()["tos_reviewer"] == "pytest"

    allowed = client.post(f"/offers/{offer_id}/evidence", json=payload)
    assert allowed.status_code == 201, allowed.text
    listed = next(s for s in client.get("/sources").json() if s["id"] == source_id)
    assert listed["tos_reviewer"] == "pytest"
    assert listed["tos_reference"] == "provider terms v3"
    assert listed["tos_reviewed_at"] is not None
    assert listed["tos_valid"] is True
    assert listed["tos_expires_at"] is not None


def test_expired_tos_review_blocks_collection(client, monkeypatch):
    import uuid
    monkeypatch.setenv("MTK_TOS_REVIEW_TTL_DAYS", "1")
    provider = f"WP01TOSEXP {uuid.uuid4()}"
    source_id = _new_source(client, provider)
    offer_id = _new_offer(client, provider)
    _attest(client, source_id)
    _run("UPDATE sources SET tos_reviewed_at = now() - interval '2 days' "
         "WHERE id = $1::uuid", source_id)

    url = "https://example.com/expired-tos"
    payload = {
        "url": url, "source_id": source_id, "official": True,
        "captured_content": SNAPSHOT_TEXT, **_procured(url, SNAPSHOT_TEXT),
    }
    blocked = client.post(f"/offers/{offer_id}/evidence", json=payload)
    assert blocked.status_code == 422, blocked.text
    assert "expired" in blocked.json()["detail"]
    listed = next(s for s in client.get("/sources").json() if s["id"] == source_id)
    assert listed["tos_valid"] is False

    _attest(client, source_id)
    allowed = client.post(f"/offers/{offer_id}/evidence", json=payload)
    assert allowed.status_code == 201, allowed.text


def test_tos_review_revocation_blocks_new_collection(client):
    import uuid
    provider = f"WP01TOSREV {uuid.uuid4()}"
    source_id = _new_source(client, provider)
    offer_id = _new_offer(client, provider)
    _attest(client, source_id)

    denied = client.delete(f"/sources/{source_id}/tos-review")
    assert denied.status_code == 403
    revoked = client.delete(f"/sources/{source_id}/tos-review",
                            params={"reviewer": "pytest"})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] is True

    url = "https://example.com/revoked-tos"
    blocked = client.post(f"/offers/{offer_id}/evidence", json={
        "url": url, "source_id": source_id, "official": True,
        "captured_content": SNAPSHOT_TEXT, **_procured(url, SNAPSHOT_TEXT),
    })
    assert blocked.status_code == 422, blocked.text
    assert "terms-of-service review" in blocked.json()["detail"]
    listed = next(s for s in client.get("/sources").json() if s["id"] == source_id)
    assert listed["tos_reviewer"] is None and listed["tos_valid"] is False

    unknown = client.delete(f"/sources/{uuid.uuid4()}/tos-review",
                            params={"reviewer": "pytest"})
    assert unknown.status_code == 404


def test_tos_requirement_opt_out_allows_legacy_sources(client, monkeypatch):
    import uuid
    monkeypatch.setenv("MTK_REQUIRE_TOS_ATTESTATION", "0")
    provider = f"WP01TOSLEGACY {uuid.uuid4()}"
    source_id = _new_source(client, provider)
    offer_id = _new_offer(client, provider)
    response = client.post(f"/offers/{offer_id}/evidence", json={
        "url": "https://example.com/legacy-tos", "source_id": source_id,
        "official": True, "captured_content": SNAPSHOT_TEXT,
        **_procured("https://example.com/legacy-tos", SNAPSHOT_TEXT),
    })
    assert response.status_code == 201, response.text


def test_tos_review_requires_a_recorded_reviewer(client):
    import uuid
    source_id = _new_source(client, f"WP01TOSR {uuid.uuid4()}")
    missing = client.post(f"/sources/{source_id}/tos-review",
                          json={"reference": "terms v1"})
    assert missing.status_code == 403
    blank = client.post(f"/sources/{source_id}/tos-review",
                        json={"reference": "   ", "reviewer": "Kashi"})
    assert blank.status_code == 422
    assert client.post(f"/sources/{source_id}/tos-review", json={
        "reference": "terms v1", "reviewer": "Kashi",
    }).status_code == 200
    unknown = client.post(f"/sources/{uuid.uuid4()}/tos-review", json={
        "reference": "terms v1", "reviewer": "Kashi",
    })
    assert unknown.status_code == 404


def test_machine_evidence_must_name_its_source(client):
    oid, _, _, _, payload = _verification_fixture(client)
    response = client.post(f"/offers/{oid}/evidence",
                           json={**payload, "source_id": None})
    assert response.status_code == 422, response.text
    assert "registered source" in response.json()["detail"]


def test_reviewer_attested_snapshot_needs_no_tos_attestation(client):
    import uuid
    provider = f"WP01HUMAN {uuid.uuid4()}"
    source_id = _new_source(client, provider)
    offer_id = _new_offer(client, provider)
    response = client.post(f"/offers/{offer_id}/evidence", json={
        "url": "https://example.com/human-terms", "source_id": source_id,
        "official": True, "captured_content": SNAPSHOT_TEXT,
        "excerpt": "reviewed by hand", "reviewer": "Kashi",
    })
    assert response.status_code == 201, response.text


def test_tos_review_migration_enforces_a_complete_attestation(client):
    """Upgrade 017→018: no attestation until all three fields are set."""
    import uuid

    async def check():
        conn = await asyncpg.connect(DSN)
        tx = conn.transaction()
        await tx.start()
        try:
            schema = "wp01_tos_" + uuid.uuid4().hex
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path TO "{schema}", public')
            paths = db_migrate.migration_files()
            target = next(p for p in paths if p.name.startswith("018_"))
            for path in paths:
                if path.name < target.name:
                    await conn.execute(path.read_text(encoding="utf-8"))
            source_id = await conn.fetchval(
                "INSERT INTO sources (provider, canonical_domain, category, adapter, trust_tier) "
                "VALUES ('TOS', 'example.com', 'student_programs', 'manual', "
                "'A_provider_owned') RETURNING id")
            await conn.execute(target.read_text(encoding="utf-8"))
            row = await conn.fetchrow(
                "SELECT tos_reviewed_at, tos_reviewer, tos_reference "
                "FROM sources WHERE id = $1", source_id)
            assert row["tos_reviewed_at"] is None and row["tos_reviewer"] is None
            with pytest.raises(asyncpg.exceptions.CheckViolationError):
                # A savepoint: the failed CHECK must not abort the outer test
                # transaction that is rolled back at the end.
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE sources SET tos_reviewed_at = now(), tos_reviewer = 'Kashi' "
                        "WHERE id = $1", source_id)
            await conn.execute(
                "UPDATE sources SET tos_reviewed_at = now(), tos_reviewer = 'Kashi', "
                "tos_reference = 'terms v1' WHERE id = $1", source_id)
            row = await conn.fetchrow(
                "SELECT tos_reviewer, tos_reference FROM sources WHERE id = $1",
                source_id)
            assert row["tos_reviewer"] == "Kashi" and row["tos_reference"] == "terms v1"
        finally:
            await tx.rollback()
            await conn.close()
    asyncio.run(check())


def test_fact_pack_is_persisted_and_returned(client):
    import uuid
    oid, field = _typed_fixture(client, "coupon")
    response = client.post(f"/offers/{oid}/extraction", json={"fields": {
        "promo_code": field("SAVE2026"),
        "eligibility": field("students"),
    }})
    assert response.status_code == 201, response.text
    body = response.json()
    pack = body["fact_pack"]
    assert pack["promo_code"]["status"] == "supported"
    assert pack["eligibility"]["status"] == "supported"
    # An unrequired, unsubmitted field is recorded as not applicable, not absent.
    assert pack["renewal"]["status"] == "not_applicable"

    stored = _run(
        "SELECT fact_pack::text AS fact_pack, offer_type FROM extractions WHERE id = $1",
        uuid.UUID(body["id"]),
    )[0]
    assert json.loads(stored["fact_pack"])["promo_code"]["status"] == "supported"
    assert stored["offer_type"] == "coupon"

    # The reviewer-facing offer response carries the same server-derived pack.
    shown = client.get(f"/offers/{oid}").json()["extraction"]["fact_pack"]
    assert json.loads(shown)["eligibility"]["status"] == "supported"


def test_fact_pack_column_accepts_only_a_json_object(client):
    import uuid
    oid, _ = _typed_fixture(client, "coupon")
    with pytest.raises(asyncpg.CheckViolationError):
        _run(
            "INSERT INTO extractions (offer_id, fields, fact_pack) VALUES ($1, '{}', '[]'::jsonb)",
            uuid.UUID(oid),
        )


def test_unknown_required_claim_blocks_promotion(client):
    """A free trial must prove billing terms; a missing one stays unknown."""
    import uuid
    oid, field = _typed_fixture(client, "free_trial")
    response = client.post(f"/offers/{oid}/extraction", json={
        "fields": {"promo_code": field("SAVE2026"), "eligibility": field("students")},
        "complete": True,
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["complete"] is False
    for missing in ("value", "benefit_type", "expiry", "renewal", "auto_renew"):
        assert body["fact_pack"][missing]["status"] == "unknown", missing
    assert any("renewal" in error for error in body["validation_errors"])
    stored = _run("SELECT complete FROM extractions WHERE id = $1", uuid.UUID(body["id"]))[0]
    assert stored["complete"] is False
    assert client.post(f"/offers/{oid}/transition", json={"to": "verified"}).status_code == 422


def test_complete_typed_offer_promotes(client):
    oid, field = _typed_fixture(client, "free_trial")
    response = client.post(f"/offers/{oid}/extraction", json={
        "fields": {
            "value": field("free trial"),
            "benefit_type": field("free"),
            "eligibility": field("students"),
            "expiry": field("31 December 2026"),
            "renewal": field("$19"),
            "auto_renew": field("yes"),
        },
        "complete": False,
        "coverage": _coverage(field.evidence_id),
    })
    assert response.status_code == 201, response.text
    assert response.json()["complete"] is True, response.json()["validation_errors"]
    assert client.post(f"/offers/{oid}/transition", json={"to": "verified"}).status_code == 200


def test_contradicted_claim_blocks_promotion(client):
    text = "Use promo code SAVE2026. Students are not eligible for this promotion."
    oid, field = _typed_fixture(client, "coupon", text)
    response = client.post(f"/offers/{oid}/extraction", json={"fields": {
        "promo_code": field("SAVE2026"),
        "eligibility": field("students"),
    }})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["complete"] is False
    assert body["fact_pack"]["eligibility"]["status"] == "contradicted"
    assert any("contradicted" in error for error in body["validation_errors"])
    assert client.post(f"/offers/{oid}/transition", json={"to": "verified"}).status_code == 422


def test_retyping_an_offer_rechecks_against_the_new_contract(client):
    """The gate re-derives against the CURRENT offer type, never the stored one."""
    oid, field = _typed_fixture(client, "coupon")
    extracted = client.post(f"/offers/{oid}/extraction", json={"fields": {
        "promo_code": field("SAVE2026"),
        "eligibility": field("students"),
    }, "coverage": _coverage(field.evidence_id)})
    assert extracted.json()["complete"] is True
    assert client.post(f"/offers/{oid}/transition", json={"to": "verified"}).status_code == 200

    patched = client.patch(f"/offers/{oid}", json={"offer_type": "free_trial"})
    assert patched.status_code == 200, patched.text
    assert client.get(f"/offers/{oid}").json()["state"] == "evidence_needed"

    result = client.post(f"/offers/{oid}/transition", json={"to": "verified"})
    assert result.status_code == 422, result.text
    assert "renewal" in result.json()["detail"]


AUTH = {"Authorization": f"Bearer {AUTH_TOKEN}"}
SVC = {"Authorization": "Bearer svc-token"}

def test_whoami_distinguishes_reviewer_service_and_anonymous(auth_client):
    r = auth_client.get("/whoami")
    assert r.status_code == 401, "no token must be rejected when auth is on"

    r = auth_client.get("/whoami", headers=SVC)
    assert r.status_code == 200 and r.json() == {"actor": None, "auth": "service"}

    r = auth_client.get("/whoami", headers=AUTH)
    assert r.status_code == 200 and r.json() == {"actor": REVIEWER, "auth": "reviewer"}


def test_reviewer_token_binds_audit_actor_over_body_strings(auth_client):
    res = auth_client.post("/offers", headers=AUTH, json={
        "provider": "Auth Test Co", "category": "domains",
        "offer_type": "free_trial", "title": "identity binding probe",
    })
    assert res.status_code == 201, res.text
    offer_id = res.json()["id"]

    # the token owner — not any body string — is the actor on record
    rows = _run("SELECT actor FROM audit_log WHERE entity = 'offers' AND entity_id = $1 "
                "ORDER BY created_at DESC LIMIT 1", __import__("uuid").UUID(offer_id))
    assert rows[0]["actor"] == REVIEWER

    # an authenticated approval no longer needs the body reviewer field (§3)
    tr = auth_client.post(f"/offers/{offer_id}/transition", headers=AUTH,
                          json={"to": "evidence_needed", "note": "probe"})
    assert tr.status_code == 200, tr.text


def test_service_token_supports_explicit_reviewer_fallback(auth_client):
    res = auth_client.post("/offers", headers=SVC, json={
        "provider": "Svc Co", "category": "domains", "offer_type": "coupon",
    })
    assert res.status_code == 201, res.text
    rows = _run("SELECT actor FROM audit_log WHERE entity = 'offers' AND entity_id = $1 "
                "ORDER BY created_at DESC LIMIT 1", __import__("uuid").UUID(res.json()["id"]))
    assert rows[0]["actor"] == "reviewer"  # dev default preserved for service callers


def test_unknown_token_rejected(auth_client):
    r = auth_client.get("/whoami", headers={"Authorization": "Bearer rtok-not-a-token"})
    assert r.status_code == 401


def test_revoked_reviewer_token_rejected(auth_client):
    auth_client.get("/whoami", headers=AUTH)  # populate the positive cache
    _run("UPDATE reviewers SET active = FALSE WHERE name = $1", REVIEWER)
    api_hardening.reset_reviewer_cache()
    r = auth_client.get("/whoami", headers=AUTH)
    assert r.status_code == 401, "revocation must take effect"


# ------------------------------------------------- v0.18: settings + metrics

def test_settings_roundtrip_and_validation(auth_client):
    assert auth_client.get("/settings/no_such_setting", headers=SVC).status_code == 404
    assert auth_client.get("/settings/publish_windows", headers=SVC).json()["value"] is None

    bad = auth_client.put("/settings/publish_windows", headers=SVC,
                          json={"value": {"windows": ["25:00", "18:00"]}})
    assert bad.status_code == 422, "out-of-range windows must be refused"

    ok = auth_client.put("/settings/publish_windows", headers=SVC,
                         json={"value": {"windows": ["09:30", "18:00", "09:30"]}})
    assert ok.status_code == 200, ok.text
    assert ok.json()["value"]["windows"] == ["09:30", "18:00"], "dedup + order preserved"

    fetched = auth_client.get("/settings/publish_windows", headers=SVC).json()
    assert fetched["value"]["windows"] == ["09:30", "18:00"]


def test_language_policy_is_english_first_and_urdu_is_opt_in(auth_client):
    current = auth_client.get("/settings/language_policy", headers=SVC)
    assert current.status_code == 200, current.text
    value = current.json()["value"]
    assert value["metadata_language"] == "en"
    assert value["captions_language"] == "en"
    assert value["narration_languages"] == ["en"]
    assert value["urdu_voiceover_enabled"] is False

    bad = auth_client.put("/settings/language_policy", headers=SVC, json={
        "value": {"narration_languages": ["en", "fr"]},
    })
    assert bad.status_code == 422, "unknown voiceover languages must be refused"

    enabled = auth_client.put("/settings/language_policy", headers=SVC, json={
        "value": {
            "metadata_language": "en",
            "captions_language": "en",
            "narration_languages": ["en", "ur"],
            "default_narration_language": "ur",
        },
    })
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["value"]["urdu_voiceover_enabled"] is True
    assert enabled.json()["value"]["metadata_language"] == "en"

    # Leave the shared test database on the English-first default.
    reset = auth_client.put("/settings/language_policy", headers=SVC, json={
        "value": {"narration_languages": ["en"], "default_narration_language": "en"},
    })
    assert reset.status_code == 200, reset.text
    assert reset.json()["value"]["urdu_voiceover_enabled"] is False


def test_metrics_ingest_upserts_one_daily_snapshot(auth_client):
    offer = auth_client.post("/offers", headers=SVC, json={
        "provider": "Metrics Co", "category": "domains", "offer_type": "coupon",
    }).json()
    sid = _run(
        """
        INSERT INTO schedules (offer_id, platform, state, local_time, timezone,
                               privacy, idempotency_key, remote_post_id, version_hash)
        VALUES ($1, 'youtube', 'published', now(), 'Asia/Karachi', 'private',
                'itest-metrics-1', 'vid-metrics-1', 'hash-metrics-1')
        RETURNING id
        """,
        __import__("uuid").UUID(offer["id"]),
    )[0]["id"]

    wrong = auth_client.post(f"/schedules/{sid}/metrics", headers=SVC, json={
        "platform": "facebook", "source": "graph-insights", "views": 1,
    })
    assert wrong.status_code == 409, "metrics platform must match the schedule"

    first = auth_client.post(f"/schedules/{sid}/metrics", headers=SVC, json={
        "platform": "youtube", "source": "youtube-analytics",
        "views": 100, "likes": 5, "comments": 2, "avg_watch_s": 90.5,
    })
    assert first.status_code == 201, first.text

    second = auth_client.post(f"/schedules/{sid}/metrics", headers=SVC, json={
        "platform": "youtube", "source": "youtube-analytics",
        "views": 150, "likes": 9, "comments": 4, "avg_watch_s": 95.0, "raw": {"n": 2},
    })
    assert second.status_code == 201

    rows = auth_client.get(f"/schedules/{sid}/metrics", headers=SVC).json()["metrics"]
    assert len(rows) == 1, "same-day re-pull must REPLACE, not duplicate"
    assert rows[0]["views"] == 150 and rows[0]["comments"] == 4


def test_analytics_content_performance_and_patch_marker(auth_client):
    offer = auth_client.post("/offers", headers=SVC, json={
        "provider": "Patch Co", "category": "domains", "offer_type": "coupon",
    }).json()
    sid = _run(
        """
        INSERT INTO schedules (offer_id, platform, state, local_time, timezone,
                               privacy, idempotency_key, remote_post_id, version_hash)
        VALUES ($1, 'youtube', 'published', now(), 'Asia/Karachi', 'private',
                'itest-patch-1', 'vid-patch-1', 'hash-patch-1')
        RETURNING id
        """,
        __import__("uuid").UUID(offer["id"]),
    )[0]["id"]

    auth_client.post(f"/schedules/{sid}/metrics", headers=SVC, json={
        "platform": "youtube", "source": "youtube-analytics", "views": 77, "likes": 3,
    })

    data = auth_client.get("/analytics", headers=SVC).json()
    totals = data["metrics_totals"]
    assert totals["posts_measured"] >= 1 and int(totals["views"]) >= 77
    perf = {str(row["id"]): row for row in data["content_performance"]}
    assert str(sid) in perf and perf[str(sid)]["views"] == 77

    not_published = _run(
        "INSERT INTO schedules (offer_id, platform, state, local_time, privacy, idempotency_key) "
        "SELECT offer_id, 'youtube', 'scheduled', now(), 'private', 'itest-patch-2' "
        "FROM schedules WHERE id = $1 RETURNING id", __import__("uuid").UUID(str(sid)))[0]["id"]
    refused = auth_client.post(f"/schedules/{not_published}/mark-description-patched", headers=SVC, json={})
    assert refused.status_code == 409, "only published posts get description patches"

    patched = auth_client.post(f"/schedules/{sid}/mark-description-patched", headers=SVC, json={})
    assert patched.status_code == 200, patched.text
    row = _run("SELECT description_patched_at FROM schedules WHERE id = $1",
               __import__("uuid").UUID(str(sid)))[0]
    assert row["description_patched_at"] is not None

    listing = auth_client.get("/schedules", params={"state": "published"}, headers=SVC).json()
    mine = [p for p in listing if str(p["id"]) == str(sid)]
    assert mine and mine[0]["description_patched_at"] is not None, \
        "the worker sweep reads this field to stay idempotent"


# --------------------------------------- v0.19: render-candidate automation queue

def test_render_candidates_gate_script_capture_and_render(auth_client):
    """The queue that lets the render worker serve itself: an offer becomes a
    candidate when it has a script + a redaction-reviewed capture and NO
    render for that exact script version."""
    offer = auth_client.post("/offers", headers=SVC, json={
        "provider": "Queue Co", "category": "domains", "offer_type": "coupon",
    }).json()
    offer_id = __import__("uuid").UUID(offer["id"])

    # script + reviewed capture, but the offer is still a candidate → no render yet
    _run("INSERT INTO offer_scripts (offer_id, version, markdown) "
         "VALUES ($1, 1, '# queue script') ON CONFLICT DO NOTHING", offer_id)
    version_hash = script_version_hash("# queue script")
    _run("INSERT INTO capture_sessions (offer_id, video_path, step_log, redaction_reviewed) "
         "VALUES ($1, 'projects/x/cap.mp4', '[]'::jsonb, TRUE)", offer_id)

    # the offer must be in a video-allowed state to be a candidate
    _run("UPDATE offers SET state = 'verified' WHERE id = $1", offer_id)

    candidates = auth_client.get("/render-candidates", headers=SVC).json()
    mine = [c for c in candidates if c["offer_id"] == offer["id"]]
    assert len(mine) == 1, "verified + script + reviewed capture = ready to render"
    assert mine[0]["script_version"] == 1
    assert mine[0]["capture_id"]

    # a render for the same script version disqualifies the offer
    created = auth_client.post(f"/offers/{offer['id']}/renders", headers=SVC, json={
        "preset": "landscape", "width": 1920, "height": 1080,
        "video_path": "projects/x/render.mp4", "script_version": 1,
        "script_version_hash": version_hash,
    })
    assert created.status_code == 201, created.text

    candidates = auth_client.get("/render-candidates", headers=SVC).json()
    mine = [c for c in candidates if c["offer_id"] == offer["id"]]
    assert mine == [], "a rendered script version must not queue again"

    # an unreviewed capture never queues
    other = auth_client.post("/offers", headers=SVC, json={
        "provider": "Queue Co 2", "category": "domains", "offer_type": "coupon",
    }).json()
    other_id = __import__("uuid").UUID(other["id"])
    _run("INSERT INTO offer_scripts (offer_id, version, markdown) "
         "VALUES ($1, 1, '# unreviewed') ON CONFLICT DO NOTHING", other_id)
    _run("INSERT INTO capture_sessions (offer_id, video_path, step_log, redaction_reviewed) "
         "VALUES ($1, 'projects/x/cap2.mp4', '[]'::jsonb, FALSE)", other_id)
    _run("UPDATE offers SET state = 'verified' WHERE id = $1", other_id)
    candidates = auth_client.get("/render-candidates", headers=SVC).json()
    assert not [c for c in candidates if c["offer_id"] == other["id"]], \
        "footage that failed redaction review must never reach the renderer"


def test_health_reports_database_and_migration_readiness(auth_client):
    """Deploy probes need more than 'the process answers': a reachable
    database with a missing migration must be visible, not a 200 that lies."""
    res = auth_client.get("/health", headers=SVC)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert body["migrations_applied"] == body["migrations_total"] > 0
    assert isinstance(body["version"], str) and body["version"]


# ------------------------------------------------- v0.22: worker locks

def test_worker_lock_is_exclusive_until_released(auth_client):
    """Two publishers must never work the same queue: the second acquisition
    is refused while the first holder is live."""
    first = auth_client.post("/locks/acquire", headers=SVC,
                             json={"name": "publishing-test", "holder": "worker-a", "ttl_s": 60})
    assert first.status_code == 200, first.text
    assert first.json()["acquired"] is True

    second = auth_client.post("/locks/acquire", headers=SVC,
                              json={"name": "publishing-test", "holder": "worker-b", "ttl_s": 60})
    assert second.json()["acquired"] is False, "a live lock must not be handed out twice"
    assert second.json()["holder"] == "worker-a"

    listed = auth_client.get("/locks", headers=SVC).json()
    assert any(l["name"] == "publishing-test" for l in listed)

    released = auth_client.post("/locks/release", headers=SVC,
                                json={"name": "publishing-test", "holder": "worker-a"})
    assert released.status_code == 200

    third = auth_client.post("/locks/acquire", headers=SVC,
                             json={"name": "publishing-test", "holder": "worker-c", "ttl_s": 60})
    assert third.json()["acquired"] is True, "after release the lock is free again"


def test_expired_lock_is_taken_over(auth_client):
    """A worker that died mid-sweep must not block the queue forever."""
    _run("INSERT INTO worker_locks (name, holder, acquired_at, expires_at) "
         "VALUES ('dead-worker', 'ghost', now() - interval '1 hour', now() - interval '30 minutes') "
         "ON CONFLICT (name) DO UPDATE SET expires_at = EXCLUDED.expires_at")
    res = auth_client.post("/locks/acquire", headers=SVC,
                           json={"name": "dead-worker", "holder": "newcomer", "ttl_s": 60})
    assert res.json()["acquired"] is True, "an expired lock must be taken over"


def test_upload_attempt_marker_blocks_a_blind_retry(auth_client):
    """v0.23: the worker announces an upload before it starts. If the outcome
    never arrives, the marker stays open so the next sweep holds the post for
    a human instead of publishing a duplicate."""
    offer = auth_client.post("/offers", headers=SVC, json={
        "provider": "Dup Co", "category": "domains", "offer_type": "coupon",
    }).json()
    offer_id = __import__("uuid").UUID(offer["id"])
    sid = _run(
        """
        INSERT INTO schedules (offer_id, platform, state, local_time, timezone,
                               privacy, idempotency_key, version_hash)
        VALUES ($1, 'youtube', 'scheduled', now(), 'Asia/Karachi', 'private',
                'itest-attempt-1', 'hash-1')
        RETURNING id
        """, offer_id)[0]["id"]

    started = auth_client.post(f"/schedules/{sid}/attempt", headers=SVC,
                               json={"detail": "upload started", "worker": "publishing-worker"})
    assert started.status_code == 200, started.text
    assert started.json()["attempt"]["started_at"]

    listing = auth_client.get("/schedules", params={"state": "scheduled"}, headers=SVC).json()
    mine = [s for s in listing if str(s["id"]) == str(sid)][0]
    detail = json.loads(mine["outcome_detail"]) if isinstance(mine["outcome_detail"], str) else mine["outcome_detail"]
    assert detail["attempt"]["detail"] == "upload started", "the marker must be visible to the worker"

    # a definite outcome clears the marker -> retrying is safe again
    reported = auth_client.post(f"/schedules/{sid}/result", headers=SVC,
                                json={"ok": False, "detail": "upload rejected"})
    assert reported.status_code == 200, reported.text
    listing = auth_client.get("/schedules", params={"state": "failed"}, headers=SVC).json()
    mine = [s for s in listing if str(s["id"]) == str(sid)][0]
    detail = json.loads(mine["outcome_detail"]) if isinstance(mine["outcome_detail"], str) else mine["outcome_detail"]
    assert detail.get("attempt") is None, "a recorded outcome must clear the attempt marker"


def test_attempt_marker_is_refused_for_non_scheduled_posts(auth_client):
    offer = auth_client.post("/offers", headers=SVC, json={
        "provider": "Dup Co 2", "category": "domains", "offer_type": "coupon",
    }).json()
    offer_id = __import__("uuid").UUID(offer["id"])
    sid = _run(
        """
        INSERT INTO schedules (offer_id, platform, state, local_time, timezone,
                               privacy, idempotency_key, version_hash)
        VALUES ($1, 'youtube', 'draft', now(), 'Asia/Karachi', 'private',
                'itest-attempt-2', 'hash-2')
        RETURNING id
        """, offer_id)[0]["id"]
    res = auth_client.post(f"/schedules/{sid}/attempt", headers=SVC, json={})
    assert res.status_code == 409, "only scheduled posts get upload attempts"


def test_hold_flag_is_stored_and_cleared_by_resume(auth_client):
    """A held post (unknown upload outcome) must not be auto-retried; an
    operator resuming it clears the hold."""
    offer = auth_client.post("/offers", headers=SVC, json={
        "provider": "Hold Co", "category": "domains", "offer_type": "coupon",
    }).json()
    offer_id = __import__("uuid").UUID(offer["id"])
    sid = _run(
        """
        INSERT INTO schedules (offer_id, platform, state, local_time, timezone,
                               privacy, idempotency_key, version_hash)
        VALUES ($1, 'youtube', 'scheduled', now(), 'Asia/Karachi', 'private',
                'itest-hold-1', 'hash-1')
        RETURNING id
        """, offer_id)[0]["id"]

    held = auth_client.post(f"/schedules/{sid}/result", headers=SVC,
                            json={"ok": False, "detail": "unknown outcome", "hold": True})
    assert held.status_code == 200, held.text
    row = _run("SELECT outcome_detail::text AS d FROM schedules WHERE id = $1",
               __import__("uuid").UUID(str(sid)))[0]
    assert json.loads(row["d"])["hold"] is True

    # the operator re-queues it (failed -> scheduled; the script must still
    # match the approved hash)
    _run("INSERT INTO offer_scripts (offer_id, version, markdown) "
         "VALUES ($1, 1, '# hold script') ON CONFLICT DO NOTHING", offer_id)
    version_hash = script_version_hash("# hold script")
    _run("UPDATE schedules SET version_hash = $2 WHERE id = $1",
         __import__("uuid").UUID(str(sid)), version_hash)
    resumed = auth_client.post(f"/schedules/{sid}/transition", headers=SVC,
                                json={"to": "scheduled", "reviewer": "pytest"})
    assert resumed.status_code == 200, resumed.text
    row = _run("SELECT outcome_detail::text AS d FROM schedules WHERE id = $1",
               __import__("uuid").UUID(str(sid)))[0]
    assert json.loads(row["d"])["hold"] is False, "resume must clear the hold"


# --------------------------------------- v0.26: automation policy + gates

def _set_policy(auth_client, body):
    res = auth_client.put("/automation/policy", headers=SVC, json={"policy": body})
    assert res.status_code == 200, res.text
    return res.json()["policy"]


def _reset_policy(auth_client):
    try:
        _set_policy(auth_client, {"mode": "assisted"})
    except AssertionError:
        pass


def test_automation_policy_roundtrip_validation_and_presets(auth_client):
    manual = _set_policy(auth_client, {"mode": "manual"})
    assert manual["mode"] == "manual"
    assert set(manual["stages"].values()) == {"human"}
    assert manual["guardrails"]["auto_retry"] is False

    bad = auth_client.put("/automation/policy", headers=SVC, json={
        "policy": {"mode": "autopilot", "guardrails": {"auto_publish_max_per_day": -1}},
    })
    assert bad.status_code == 422, "invalid guardrails must be refused"

    bad_stage = auth_client.put("/automation/policy", headers=SVC, json={
        "policy": {"stages": {"verify": "sometimes"}},
    })
    assert bad_stage.status_code == 422

    preset = auth_client.post("/automation/preset/autopilot", headers=SVC)
    assert preset.status_code == 200, preset.text
    assert set(preset.json()["policy"]["stages"].values()) == {"auto"}

    status = auth_client.get("/automation/status", headers=SVC)
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["summary"]["mode"] == "autopilot"
    assert "budget" in body and "queue" in body

    # the generic keyed settings route accepts (and validates) the same policy
    via_settings = auth_client.put("/settings/automation_policy", headers=SVC,
                                   json={"value": {"mode": "assisted"}})
    assert via_settings.status_code == 200, via_settings.text
    assert via_settings.json()["value"]["mode"] == "assisted"
    fetched_setting = auth_client.get("/settings/automation_policy", headers=SVC)
    assert fetched_setting.json()["value"]["stages"]["approve"] == "human"

    paused = auth_client.post("/automation/pause", headers=SVC, json={"note": "test"})
    assert paused.json()["policy"]["paused"] is True
    # choosing a mode must not silently clear the kill switch
    still_paused = auth_client.post("/automation/preset/assisted", headers=SVC)
    assert still_paused.json()["policy"]["paused"] is True
    resumed = auth_client.post("/automation/resume", headers=SVC)
    assert resumed.json()["policy"]["paused"] is False
    _reset_policy(auth_client)


def test_human_stage_refuses_automation_actor(auth_client):
    _run(
        "INSERT INTO sources (provider, canonical_domain, category, adapter, trust_tier) "
        "VALUES ('Gate Co', 'gate.example', 'domains', 'manual', 'A_provider_owned')"
    )
    offer = auth_client.post("/offers", headers=SVC, json={
        "provider": "Gate Co", "category": "domains", "offer_type": "coupon",
    }).json()
    offer_id = offer["id"]

    auth_client.post(f"/offers/{offer_id}/transition", headers=SVC,
                     json={"to": "evidence_needed", "reviewer": "pytest"})
    terms = "Free for new customers until 31 Dec 2026."
    evidence = auth_client.post(f"/offers/{offer_id}/evidence", headers=SVC, json={
        "url": "https://gate.example/terms",
        "official": True,
        "excerpt": terms,
        "captured_content": terms,
        "reviewer": "pytest",
        "supported_fields": ["value", "eligibility"],
    })
    assert evidence.status_code == 201, evidence.text
    evidence_id = evidence.json()["id"]
    extraction = auth_client.post(f"/offers/{offer_id}/extraction", headers=SVC, json={
        "fields": {
            "value": {"value": "free", "evidence_id": evidence_id,
                      "evidence_url": "https://gate.example/terms", "excerpt": terms},
            "eligibility": {"value": "new customers", "evidence_id": evidence_id,
                            "evidence_url": "https://gate.example/terms", "excerpt": terms},
        },
        "complete": True,
        "conflicts": [],
    })
    assert extraction.status_code == 201, extraction.text

    # manual mode: automation:verify is refused exactly like an anonymous actor
    _set_policy(auth_client, {"mode": "manual"})
    denied = auth_client.post(f"/offers/{offer_id}/transition", headers=SVC,
                              json={"to": "verified", "reviewer": "automation:verify"})
    assert denied.status_code == 403, denied.text
    assert "human control" in denied.json()["detail"]

    # autopilot: the same call passes the automation policy + quality gates
    _set_policy(auth_client, {"mode": "autopilot"})
    verified = auth_client.post(f"/offers/{offer_id}/transition", headers=SVC,
                                json={"to": "verified", "reviewer": "automation:verify"})
    assert verified.status_code == 200, verified.text

    # unattended approval refuses to run before a rendered, reviewed capture exists
    early = auth_client.post(f"/offers/{offer_id}/transition", headers=SVC,
                             json={"to": "approved_for_video", "reviewer": "automation:approve"})
    assert early.status_code == 422, early.text
    assert "automation approval refused" in early.json()["detail"]

    # human workflow produces the package (script -> capture -> redaction -> render)
    script = auth_client.post(f"/offers/{offer_id}/script", headers=SVC,
                              params={"created_by": "pytest"})
    assert script.status_code == 201, script.text
    capture = auth_client.post(f"/offers/{offer_id}/captures", headers=SVC, json={
        "video_path": "projects/x/cap.mp4",
        "step_log": [{"step": "open official page", "note": "no secrets"}],
    })
    assert capture.status_code == 201, capture.text
    reviewed = auth_client.post(f"/captures/{capture.json()['id']}/redaction-review",
                                headers=SVC, json={"approved": True, "reviewer": "pytest"})
    assert reviewed.status_code == 200, reviewed.text

    scripts = auth_client.get(f"/offers/{offer_id}/scripts", headers=SVC).json()
    render = auth_client.post(f"/offers/{offer_id}/renders", headers=SVC, json={
        "preset": "landscape", "width": 1920, "height": 1080,
        "video_path": "projects/x/render.mp4",
        "script_version": scripts[0]["version"],
        "script_version_hash": scripts[0]["version_hash"],
        "capture_id": capture.json()["id"],
    })
    assert render.status_code == 201, render.text

    approved = auth_client.post(f"/offers/{offer_id}/transition", headers=SVC,
                                json={"to": "approved_for_video",
                                      "reviewer": "automation:approve"})
    assert approved.status_code == 200, approved.text

    # automation-scheduled post walks draft -> needs_approval -> approved -> scheduled
    slot = auth_client.get("/automation/next-slot", headers=SVC,
                           params={"platform": "youtube"})
    assert slot.status_code == 200, slot.text
    schedule = auth_client.post(f"/offers/{offer_id}/schedules", headers=SVC, json={
        "platform": "youtube",
        "local_time": slot.json()["local_time"],
        "privacy": slot.json()["privacy"],
    })
    assert schedule.status_code == 201, schedule.text
    sid = schedule.json()["id"]

    step = auth_client.post(f"/schedules/{sid}/transition", headers=SVC,
                            json={"to": "needs_approval"})
    assert step.status_code == 200, step.text
    step = auth_client.post(f"/schedules/{sid}/transition", headers=SVC,
                            json={"to": "approved", "reviewer": "automation:approve"})
    assert step.status_code == 200, step.text
    step = auth_client.post(f"/schedules/{sid}/transition", headers=SVC,
                            json={"to": "scheduled", "reviewer": "automation:schedule"})
    assert step.status_code == 200, step.text

    # resuming a paused post stays human-only even in autopilot
    assert auth_client.post(f"/schedules/{sid}/pause", headers=SVC).status_code == 200
    denied_resume = auth_client.post(f"/schedules/{sid}/resume", headers=SVC,
                                     params={"reviewer": "automation:schedule"})
    assert denied_resume.status_code == 403, denied_resume.text
    assert "named human" in denied_resume.json()["detail"]
    denied_transition = auth_client.post(f"/schedules/{sid}/transition", headers=SVC,
                                         json={"to": "scheduled",
                                               "reviewer": "automation:schedule"})
    assert denied_transition.status_code == 403, denied_transition.text
    assert auth_client.post(f"/schedules/{sid}/resume", headers=SVC,
                            params={"reviewer": "pytest"}).status_code == 200

    # automation cannot mark an offer published directly: only a publishing
    # result may do that, so the stage map deliberately has no 'published'.
    direct_publish = auth_client.post(f"/offers/{offer_id}/transition", headers=SVC,
                                      json={"to": "published",
                                            "reviewer": "automation:approve"})
    assert direct_publish.status_code == 403, direct_publish.text
    assert "may not perform" in direct_publish.json()["detail"]

    # the platform allowlist and privacy guardrail are re-checked at scheduling
    # time, not just when the worker asks for the next slot.
    _set_policy(auth_client, {"guardrails": {"auto_schedule_platforms": ["youtube"]}})
    facebook = auth_client.post(f"/offers/{offer_id}/schedules", headers=SVC, json={
        "platform": "facebook",
        "local_time": "2027-01-01T13:00:00+00:00",
        "privacy": "private",
    })
    assert facebook.status_code == 201, facebook.text
    fb_id = facebook.json()["id"]
    auth_client.post(f"/schedules/{fb_id}/transition", headers=SVC,
                     json={"to": "needs_approval"})
    allowed = auth_client.post(f"/schedules/{fb_id}/transition", headers=SVC,
                               json={"to": "approved", "reviewer": "automation:approve"})
    assert allowed.status_code == 200, allowed.text
    refused = auth_client.post(f"/schedules/{fb_id}/transition", headers=SVC,
                               json={"to": "scheduled", "reviewer": "automation:schedule"})
    assert refused.status_code == 409, refused.text
    assert "may not schedule" in refused.json()["detail"]

    # the daily budget is enforced server-side (0 = no more unattended approvals)
    _set_policy(auth_client, {"guardrails": {"auto_publish_max_per_day": 0}})
    schedule2 = auth_client.post(f"/offers/{offer_id}/schedules", headers=SVC, json={
        "platform": "youtube",
        "local_time": "2027-01-02T13:00:00+00:00",
        "privacy": "private",
    })
    if schedule2.status_code == 201:
        sid2 = schedule2.json()["id"]
        auth_client.post(f"/schedules/{sid2}/transition", headers=SVC,
                         json={"to": "needs_approval"})
        exhausted = auth_client.post(f"/schedules/{sid2}/transition", headers=SVC,
                                     json={"to": "approved",
                                           "reviewer": "automation:approve"})
        assert exhausted.status_code == 429, exhausted.text
        assert "budget" in exhausted.json()["detail"]

    _reset_policy(auth_client)
