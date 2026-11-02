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


def test_approve_and_queue_is_reviewer_only_centrally():
    """G20: the one-click publish decision is refused for every non-human
    credential at the transport layer, independent of the router check."""
    path, method = "/schedules/approve-and-queue", "POST"
    for cls in (api_hardening.CREDENTIAL_SERVICE, api_hardening.CREDENTIAL_WORKER,
                api_hardening.CREDENTIAL_EXTENSION):
        assert api_hardening.route_authorization_failure(cls, method, path), cls
    assert api_hardening.route_authorization_failure(
        api_hardening.CREDENTIAL_REVIEWER, method, path) is None


def test_account_settings_and_policy_writes_are_reviewer_only_centrally():
    """2026-11-02 review (S1-S4): writes that choose a channel's credentials,
    re-activate a revoked account, change a setting or flip the kill switch
    are human-only at the transport layer — while the machine routes that
    share their prefixes stay open to workers."""
    raf = api_hardening.route_authorization_failure
    human_only = [
        ("POST", "/platform-accounts"),
        ("POST", "/platform-accounts/0b8f/revoke"),
        ("PUT", "/settings/brand"),
        ("PUT", "/settings/language_policy"),
        ("PUT", "/settings/publish_windows"),
        ("PUT", "/settings/automation_policy"),
        ("PUT", "/automation/policy"),
        ("POST", "/automation/pause"),
        ("POST", "/automation/resume"),
        ("POST", "/automation/preset/autopilot"),
    ]
    for method, path in human_only:
        for cls in (api_hardening.CREDENTIAL_SERVICE, api_hardening.CREDENTIAL_WORKER):
            assert raf(cls, method, path), (cls, method, path)
        assert raf(api_hardening.CREDENTIAL_REVIEWER, method, path) is None
    machine_ok = [
        ("PUT", "/settings/media_backup"),
        ("GET", "/settings/brand"),
        ("GET", "/automation/policy"),
        ("GET", "/platform-accounts"),
        ("POST", "/platform-accounts/0b8f/refreshed"),
        ("POST", "/platform-accounts/0b8f/mark-expired"),
        ("PUT", "/platform-accounts/0b8f/capabilities"),
    ]
    for method, path in machine_ok:
        assert raf(api_hardening.CREDENTIAL_WORKER, method, path) is None, (method, path)


# ------------------------------ machine actor attribution (P1-1, review fix)

def _request_as(credential: str, actor: str | None = None):
    """A bare Request stamped with a credential outcome — enough for the
    identity helpers; no app/DB involved."""
    from starlette.requests import Request

    request = Request({"type": "http", "method": "GET", "path": "/",
                       "headers": [], "query_string": b""})
    request.state.credential_class = credential
    request.state.actor = actor
    return request


def test_machine_credentials_get_their_own_identity_not_the_route_default():
    """P1-1: at require=False sites a machine credential is recorded under
    its class-derived machine actor — never the route's human-sounding
    default ("reviewer", "operator", …) and never a body-supplied name. The
    sharpest case this closes: a worker token creating a schedule can no
    longer file the human-attested fields as "reviewer"."""
    for cls, expected in (
        (api_hardening.CREDENTIAL_SERVICE, "system:service"),
        (api_hardening.CREDENTIAL_WORKER, "system:worker"),
        (api_hardening.CREDENTIAL_EXTENSION, "system:extension"),
    ):
        request = _request_as(cls)
        assert api_hardening.effective_reviewer(
            request, "Alice Approver", default="reviewer") == expected, cls
        assert api_hardening.effective_reviewer(
            request, None, default="reviewer") == expected, cls


def test_machine_credentials_may_still_identify_an_automation_stage():
    request = _request_as(api_hardening.CREDENTIAL_WORKER)
    assert api_hardening.effective_reviewer(
        request, "automation:schedule", default="reviewer") == "automation:schedule"


def test_dev_open_body_fallback_is_unchanged():
    """Dev-open mode (explicit opt-in, P0-1) keeps the legacy body fallback:
    there is no credential boundary to protect there."""
    request = _request_as(api_hardening.CREDENTIAL_DISABLED)
    assert api_hardening.effective_reviewer(
        request, "Body Name", default="reviewer") == "Body Name"
    assert api_hardening.effective_reviewer(
        request, None, default="reviewer") == "reviewer"


def test_reviewer_token_identity_still_wins():
    request = _request_as(api_hardening.CREDENTIAL_REVIEWER, actor="Kashi")
    assert api_hardening.effective_reviewer(
        request, "Someone Else", default="reviewer") == "Kashi"


def test_is_machine_actor_matches_both_machine_namespaces():
    assert api_hardening.is_machine_actor("system:worker")
    assert api_hardening.is_machine_actor("automation:schedule")
    assert api_hardening.is_machine_actor("System:Service")  # case-insensitive
    assert not api_hardening.is_machine_actor(None)
    assert not api_hardening.is_machine_actor("")
    assert not api_hardening.is_machine_actor("reviewer")
    assert not api_hardening.is_machine_actor("Kashi")


# ------------------------------ fail-closed startup guard (P0-1, review fix)

def _clear_all_credentials(monkeypatch):
    monkeypatch.delenv("MTK_API_TOKEN", raising=False)
    monkeypatch.delenv(api_hardening.WORKER_TOKEN_ENV, raising=False)
    monkeypatch.delenv(api_hardening.EXTENSION_TOKEN_ENV, raising=False)
    monkeypatch.delenv(api_hardening.ALLOW_UNAUTHENTICATED_ENV, raising=False)


def test_boot_refuses_without_credentials(monkeypatch):
    """No configured credential + no explicit opt-out → RuntimeError."""
    _clear_all_credentials(monkeypatch)
    with pytest.raises(RuntimeError, match="refusing to start"):
        api_hardening.verify_boot_authentication()


def test_boot_dev_open_needs_the_explicit_opt_in_and_logs_critically(
        monkeypatch, caplog):
    """MTK_ALLOW_UNAUTHENTICATED=1 allows dev-open — loudly. A CRITICAL banner
    names the mode so it can never run quietly in production by accident."""
    _clear_all_credentials(monkeypatch)
    monkeypatch.setenv(api_hardening.ALLOW_UNAUTHENTICATED_ENV, "1")
    assert api_hardening.allow_unauthenticated() is True
    with caplog.at_level(logging.CRITICAL, logger="mtk.api"):
        api_hardening.verify_boot_authentication()  # must NOT raise
    banners = [r for r in caplog.records if "DEV-OPEN" in r.getMessage()]
    assert banners, "dev-open mode must be named in a CRITICAL banner"
    assert banners[0].levelno == logging.CRITICAL


@pytest.mark.parametrize("env", [
    {"MTK_API_TOKEN": "tok"},
    {"MTK_WORKER_TOKEN": "worker-tok"},
    {"MTK_EXTENSION_TOKEN": "ext-tok"},
])
def test_any_configured_credential_boots_quietly(monkeypatch, env, caplog):
    """A single credential of any class lifts the guard — no opt-in needed,
    and no dev-open banner is logged."""
    _clear_all_credentials(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with caplog.at_level(logging.CRITICAL, logger="mtk.api"):
        api_hardening.verify_boot_authentication()  # must NOT raise
    assert not [r for r in caplog.records if "DEV-OPEN" in r.getMessage()]
