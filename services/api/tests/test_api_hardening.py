"""API hardening tests (v0.13).

- auth middleware: token on/off,OPEN_PATHS, malformed/invalid/valid headers
- request log middleware: emits one structured line per request
- analytics: regression for the v0.12 bug where _rows() lost its pool argument
  and every /analytics request 500ed — run against a fake pool, no database.
"""

import asyncio
import logging
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
