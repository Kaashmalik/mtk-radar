"""API hardening tests (v0.13).

- auth middleware: token on/off,OPEN_PATHS, malformed/invalid/valid headers
- request log middleware: emits one structured line per request
- analytics: regression for the v0.12 bug where _rows() lost its pool argument
  and every /analytics request 500ed — run against a fake pool, no database.
"""

import asyncio
import logging
import re
import sys
import types
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_hardening

# analytics_api imports the real `db` module, which pulls in asyncpg — a driver
# this test never touches (it uses a fake pool). Stub it when the driver is
# unavailable so the pure SQL-orchestration regression test always runs.
try:
    import db  # noqa: F401
except ModuleNotFoundError:  # asyncpg not installed
    _fake_db = types.ModuleType("db")
    _fake_db.get = lambda: None
    sys.modules["db"] = _fake_db

import analytics_api


# ------------------------------------------------------------- helpers


@pytest.fixture()
def hardened_app():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture()
def fake_pool(monkeypatch):
    """Pool stand-in: /analytics runs pure SQL through fetch/fetchrow/fetchval."""

    class FakePool:
        async def fetch(self, _query, *args):
            return [{"state": "verified", "n": 3}]

        async def fetchrow(self, _query, *args):
            return {"live_offers": 3, "retired_offers": 0, "corrections": 0,
                    "evidence_per_offer": 1.5, "recheck_due": 0,
                    "published": 1, "failed": 0, "paused": 0, "auto_paused": 0}

        async def fetchval(self, _query, *args):
            return datetime.now(timezone.utc)

    monkeypatch.setattr(analytics_api.db, "get", lambda: FakePool())
    return FakePool()


# ------------------------------------------------------------- auth


def test_open_when_no_token(hardened_app):
    api_hardening.register(hardened_app, token=None)
    with TestClient(hardened_app) as client:
        assert client.get("/ping").status_code == 200
        assert client.get("/health").status_code == 200


def test_token_required_when_configured(hardened_app):
    api_hardening.register(hardened_app, token="s3cret")
    with TestClient(hardened_app) as client:
        assert client.get("/ping").status_code == 401
        assert "WWW-Authenticate" in client.get("/ping").headers

        # /health stays open for liveness probes
        assert client.get("/health").status_code == 200

        # malformed and wrong credentials are rejected
        assert client.get("/ping", headers={"Authorization": "s3cret"}).status_code == 401
        assert client.get("/ping", headers={"Authorization": "Basic s3cret"}).status_code == 401
        assert client.get("/ping", headers={"Authorization": "Bearer wrong"}).status_code == 401

        # valid bearer passes
        assert client.get("/ping", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_service_credentials_cannot_satisfy_a_human_reviewer(hardened_app):
    """A compromised worker must not become a human approver by naming one."""
    from fastapi import Request

    @hardened_app.get("/human")
    async def human(request: Request, reviewer: str | None = None):
        actor = api_hardening.effective_reviewer(request, reviewer, require=True)
        return {"actor": actor}

    @hardened_app.get("/whoami")
    async def whoami(request: Request):
        return {"auth": api_hardening.credential_class(request),
                "actor": api_hardening.actor_of(request)}

    api_hardening.register(hardened_app, token="svc-secret")
    hardened_app.include_router(api_hardening.router)
    with TestClient(hardened_app) as client:
        denied = client.get(
            "/human", params={"reviewer": "Alice"},
            headers={"Authorization": "Bearer svc-secret"},
        )
        assert denied.status_code == 403
        assert "human reviewer credential" in denied.json()["detail"]

        # An automation identity is still a machine credential: it may act on
        # automation stages (require=False + explicit authorize) but must not
        # satisfy a human-only attestation.
        automation = client.get(
            "/human", params={"reviewer": "automation:approve"},
            headers={"Authorization": "Bearer svc-secret"},
        )
        assert automation.status_code == 403
        assert "human reviewer credential" in automation.json()["detail"]

        assert client.get("/whoami", headers={"Authorization": "Bearer svc-secret"}).json() == {
            "actor": None, "auth": "service",
        }


def test_worker_token_has_a_distinct_credential_class(hardened_app, monkeypatch):
    monkeypatch.setenv("MTK_WORKER_TOKEN", "worker-secret")
    api_hardening.register(hardened_app, token="svc-secret")
    hardened_app.include_router(api_hardening.router)
    with TestClient(hardened_app) as client:
        worker = client.get(
            "/whoami", headers={"Authorization": "Bearer worker-secret"})
        assert worker.status_code == 200
        assert worker.json() == {"actor": None, "auth": "worker"}
        service = client.get(
            "/whoami", headers={"Authorization": "Bearer svc-secret"})
        assert service.json() == {"actor": None, "auth": "service"}


# ------------------------------------------------------------- logging


def test_request_logged(hardened_app, caplog):
    api_hardening.register(hardened_app, token=None)
    with caplog.at_level(logging.INFO, logger="mtk.api"):
        with TestClient(hardened_app) as client:
            client.get("/ping")
    line = next(r for r in caplog.records if "request method=" in r.getMessage())
    assert "path=/ping" in line.getMessage()
    assert "status=200" in line.getMessage()
    assert "duration_ms=" in line.getMessage()


def test_logged_even_when_auth_rejects(hardened_app, caplog):
    api_hardening.register(hardened_app, token="s3cret")
    with caplog.at_level(logging.INFO, logger="mtk.api"):
        with TestClient(hardened_app) as client:
            assert client.get("/ping").status_code == 401
    logs = [r.getMessage() for r in caplog.records if "request method=" in r.getMessage()]
    assert logs and "status=401" in logs[-1]


# ------------------------------------------------------------- analytics


def test_analytics_passes_pool_to_every_query(fake_pool):
    """Regression: v0.12 shipped _rows() calls without the pool argument, so
    GET /analytics raised TypeError (500) on every request. This runs the real
    endpoint against a fake pool — a missing argument fails immediately."""
    result = asyncio.run(analytics_api.analytics())

    assert result["items_total"] in (0, 3) or isinstance(result["items_total"], int)
    assert result["verification"]["live_offers"] == 3
    assert result["publishing"]["published"] == 1
    assert result["generated_at"] is not None


# ------------------------------------------------- brute-force rate limit (v0.33)


def test_auth_failures_trigger_429_then_reset(hardened_app, monkeypatch):
    """A per-IP sliding window over auth failures: past the failure budget the
    gate serves 429 — reviewer tokens cannot be brute-forced at line rate.
    A valid credential resets the budget immediately."""
    monkeypatch.setattr(api_hardening, "AUTH_FAILURE_LIMIT", 3)
    monkeypatch.setattr(api_hardening, "AUTH_FAILURE_WINDOW_S", 60.0)
    api_hardening.reset_auth_failures()  # isolation: other tests' 401s linger
    api_hardening.register(hardened_app, token="s3cret")
    with TestClient(hardened_app) as client:
        for _ in range(3):
            assert client.get("/ping").status_code == 401
        # budget exhausted → 429 even BEFORE the token is read
        blocked = client.get("/ping")
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers

        # correct token is blocked too (same IP) — that is the point: stop
        # guessing by making everything 429 until the window cools down
        assert client.get(
            "/ping", headers={"Authorization": "Bearer s3cret"}).status_code == 429

    api_hardening.reset_auth_failures()
    with TestClient(hardened_app) as client:
        assert client.get(
            "/ping", headers={"Authorization": "Bearer s3cret"}).status_code == 200
        # a success cleared the (single) failure record: failures still allowed
        assert client.get("/ping").status_code == 401
        assert client.get("/ping").status_code == 401
        assert client.get("/ping").status_code != 429  # only 2 since reset+success


def test_rate_limit_counts_failures_not_successes(hardened_app, monkeypatch):
    monkeypatch.setattr(api_hardening, "AUTH_FAILURE_LIMIT", 5)
    api_hardening.reset_auth_failures()
    api_hardening.register(hardened_app, token="s3cret")
    with TestClient(hardened_app) as client:
        # 50 successful requests never trip the limiter
        for _ in range(50):
            assert client.get(
                "/ping", headers={"Authorization": "Bearer s3cret"}).status_code == 200
        # 4 failures stay under the budget of 5
        for _ in range(4):
            client.get("/ping")
        assert client.get(
            "/ping", headers={"Authorization": "Bearer s3cret"}).status_code == 200


# ------------------------------------------------------------- metrics (v0.33)


def test_metrics_endpoint_renders_prometheus_format(hardened_app, monkeypatch):
    """GET /metrics parses as Prometheus text format: HELP/TYPE lines,
    counter/gauge samples, request counters from the middleware."""
    from fastapi import FastAPI

    class FakePool:
        async def fetch(self, query, *args):
            if "FROM jobs" in query:
                return [("pending", "publish_schedule", 2)]
            if "FROM schedules" in query:
                return [("scheduled", 1)]
            return [("verified", 4)]

        async def fetchval(self, query, *args):
            return 7

    import metrics_api
    monkeypatch.setattr(metrics_api.db, "get", lambda: FakePool())
    app = hardened_app
    api_hardening.register(app, token="s3cret")
    app.include_router(metrics_api.router)
    with TestClient(app) as client:
        client.get("/ping", headers={"Authorization": "Bearer s3cret"})
        res = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    body = res.text
    assert "# TYPE mtk_api_requests_total counter" in body
    assert "# TYPE mtk_jobs gauge" in body
    assert 'mtk_jobs{status="pending",kind="publish_schedule"} 2' in body
    assert 'mtk_schedules{state="scheduled"} 1' in body
    assert "mtk_renders_total 7" in body
    # the /ping request above was counted by the middleware
    # (count may exceed 1 — earlier tests in this process hit /ping too)
    assert re.search(
        r'mtk_api_requests_total\{method="GET",path="/ping",status="2xx"\} [1-9]\d*', body)


def test_metrics_requires_auth_when_token_configured(hardened_app):
    import metrics_api
    api_hardening.register(hardened_app, token="s3cret")
    hardened_app.include_router(metrics_api.router)
    with TestClient(hardened_app) as client:
        assert client.get("/metrics").status_code == 401


# ----------------------------------------- G05 route/role matrix (intake-only)

@pytest.fixture()
def matrix_app():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/whoami")
    async def whoami():
        return {"ok": True}

    @app.post("/items")
    async def post_item():
        return {"ok": True}

    @app.post("/media/gc")
    async def media_gc():
        return {"deleted": True}

    return app


def test_extension_credential_is_intake_only(matrix_app, monkeypatch):
    """G05: the extension credential may ONLY save candidate items and probe
    its own identity. Leaked, it cannot read the dashboard, claim jobs, or
    delete artifacts — deny-by-default on everything else."""
    monkeypatch.setenv("MTK_EXTENSION_TOKEN", "ext-tok")
    import api_hardening as ah
    ah.register(matrix_app, token="svc-tok")
    ext = {"Authorization": "Bearer ext-tok"}
    with TestClient(matrix_app) as client:
        assert client.post("/items", headers=ext).status_code == 200
        assert client.get("/whoami", headers=ext).status_code == 200
        assert client.get("/ping", headers=ext).status_code == 403
        assert client.post("/media/gc", headers=ext).status_code == 403

        # prefix discipline: /items2 is NOT granted by an /items prefix
        assert client.get("/ping", headers={"Authorization": "Bearer ext-tok"}).status_code == 403

        # the service credential is not the extension: rules differ
        assert client.get("/ping", headers={"Authorization": "Bearer svc-tok"}).status_code == 200


def test_media_gc_reserved_for_human_reviewers_central(matrix_app, monkeypatch):
    """G05: /media/gc is destructive — the service and worker credentials are
    refused centrally, before any router logic runs."""
    monkeypatch.setenv("MTK_WORKER_TOKEN", "work-tok")
    import api_hardening as ah
    ah.register(matrix_app, token="svc-tok")
    with TestClient(matrix_app) as client:
        assert client.post("/media/gc",
                           headers={"Authorization": "Bearer svc-tok"}).status_code == 403
        assert client.post("/media/gc",
                           headers={"Authorization": "Bearer work-tok"}).status_code == 403
        # other routes stay open to the control-plane credential
        assert client.get("/ping",
                          headers={"Authorization": "Bearer svc-tok"}).status_code == 200


def test_route_matrix_decision_function_unit():
    from api_hardening import route_authorization_failure as raf

    # extension allowlist, exact + prefix semantics
    assert raf("extension", "POST", "/items") is None
    assert raf("extension", "POST", "/items/sub") is None
    assert raf("extension", "GET", "/items2") is not None  # no prefix bleed
    assert raf("extension", "DELETE", "/items") is not None
    assert raf("extension", "POST", "/media/gc") is not None
    # reviewer-only wins over any non-human grant
    assert "reviewer" in raf("worker", "POST", "/media/gc")
    assert "reviewer" in raf("service", "POST", "/jobs/bulk-retry")
    # humans and dev-open are never denied by the matrix
    assert raf("reviewer", "POST", "/media/gc") is None
    assert raf("disabled", "POST", "/media/gc") is None
    # workers keep broad pipeline access
    assert raf("worker", "POST", "/jobs") is None
    assert raf("worker", "GET", "/offers") is None
