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
import importlib.util
import os
import sys as _sys
from pathlib import Path

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


# ------------------------------------------------- v0.16: identity + approval integrity

import secrets

import fastapi

import api_hardening
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
              _settings_router, _analytics_router, _health_router, _locks_router):
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
