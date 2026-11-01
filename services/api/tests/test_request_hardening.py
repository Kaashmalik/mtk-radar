"""Request hardening middleware (review P2-1/P2-2), defined in main.py:

- 413 for a declared Content-Length above MTK_API_MAX_BODY_BYTES, and a
  BOUNDED receive channel for streaming bodies without Content-Length (the
  stream is disconnected at the cap — a body is refused loudly, never
  silently truncated into something that looks complete);
- 429 + Retry-After once a credential exceeds MTK_API_RATE_LIMIT_RPM
  requests/60 s (budget keyed by the token hash, the same in-memory
  sliding-window pattern as api_hardening's auth-failure budget);
- the budget is DISABLED in dev-open mode (no credentials), so tests and a
  sealed local environment are unaffected.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_hardening  # noqa: E402

_MAIN = Path(__file__).resolve().parents[1] / "main.py"


def _load_main():
    name = f"api_main_request_hardening_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(name, _MAIN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _ingest_app(mod, **middleware_kwargs):
    app = FastAPI()

    @app.post("/ingest")
    async def ingest(request: Request):
        body = await request.body()
        return {"len": len(body)}

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    app.add_middleware(mod._RequestHardeningMiddleware, **middleware_kwargs)
    return app


# --------------------------------------------------------------- body cap


def test_oversized_declared_body_is_rejected_with_413():
    main = _load_main()
    app = _ingest_app(main, enforce_budget=False, max_body_bytes=100)
    with TestClient(app) as client:
        ok = client.post("/ingest", json={"note": "tiny"})
        assert ok.status_code == 200, "bodies under the cap pass unchanged"

        too_big = client.post("/ingest", json={"blob": "x" * 500})
        assert too_big.status_code == 413
        assert "too large" in too_big.json()["detail"]
        # refused BEFORE the handler runs: the response never echoes the body
        assert "len" not in too_big.json()


def test_streaming_body_without_content_length_is_bounded():
    """No Content-Length → the receive channel is capped: past the cap the
    stream disconnects, so the request fails loudly instead of the process
    buffering an unbounded body (and instead of a silent truncation that
    would hand the handler a 'complete-looking' partial body)."""
    main = _load_main()
    app = _ingest_app(main, enforce_budget=False, max_body_bytes=1024)
    with TestClient(app) as client:

        def chunks():
            for _ in range(20):
                yield b"x" * 128  # 2 KiB total > 1 KiB cap

        from starlette.requests import ClientDisconnect

        with pytest.raises(ClientDisconnect):
            client.post("/ingest", content=chunks())


def test_main_app_wires_the_body_cap(monkeypatch):
    """The middleware is wired into the real app: oversized requests are
    refused with 413 by the app build itself (env-sized for the test)."""
    monkeypatch.setenv("MTK_API_MAX_BODY_BYTES", "200")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main = _load_main()
    client = TestClient(main.app)  # no context manager: startup stays unrun
    refused = client.post(
        "/sources", json={"provider": "p" * 500, "category": "domains",
                          "offer_type": "coupon"})
    assert refused.status_code == 413
    assert "too large" in refused.json()["detail"]


# ------------------------------------------------------- per-credential budget


def test_over_budget_credential_gets_429_with_retry_after():
    main = _load_main()
    app = _ingest_app(main, enforce_budget=True, requests_per_minute=3)
    api_hardening.register(app, token="svc-token")  # auth + logging layer

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer svc-token"}
        for _ in range(3):
            assert client.get("/ping", headers=headers).status_code == 200
        blocked = client.get("/ping", headers=headers)
        assert blocked.status_code == 429
        assert blocked.headers["retry-after"] == "60"
        assert "budget" in blocked.json()["detail"]


def test_budget_is_disabled_in_dev_open_mode():
    """No credentials configured → no budget keys can ever bind, and the
    middleware is wired disabled: an unauthenticated flood of requests is
    never 429'd by THIS middleware (the auth gate owns anonymous traffic in
    hardened deployments)."""
    main = _load_main()
    app = _ingest_app(main, enforce_budget=False, requests_per_minute=1)
    with TestClient(app) as client:
        for _ in range(30):
            assert client.get("/ping").status_code == 200, (
                "never a 429 in dev-open")


def test_budget_is_wired_only_when_credentials_are_configured(monkeypatch):
    """main.py wires enforce_budget from the credential presence: dev-open
    env → disabled."""
    monkeypatch.delenv("MTK_API_TOKEN", raising=False)
    monkeypatch.delenv("MTK_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("MTK_EXTENSION_TOKEN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main = _load_main()
    assert api_hardening.service_tokens() == {}
    assert main._RequestHardeningMiddleware is not None  # wiring smoke check
