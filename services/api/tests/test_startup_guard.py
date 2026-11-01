"""Fail-closed startup policy (review P0-1 / P2-3), wired from main.py
startup: without credentials the app refuses to boot unless
MTK_ALLOW_UNAUTHENTICATED=1 is explicit, and a missing DATABASE_URL fails
fast instead of silently using a hardcoded local postgres DSN.

main.py is exec'd fresh per test (the repo's established pattern — see
test_cors.py) so each case controls the module-level environment reads.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_MAIN = Path(__file__).resolve().parents[1] / "main.py"


def _load_main():
    name = f"api_main_startup_guard_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(name, _MAIN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _clear_boot_env(monkeypatch):
    for var in ("MTK_API_TOKEN", "MTK_WORKER_TOKEN", "MTK_EXTENSION_TOKEN",
                "MTK_ALLOW_UNAUTHENTICATED", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)


def test_startup_raises_without_credentials_and_without_opt_in(monkeypatch):
    """P0-1: no-credentials + no opt-out → the app refuses to START, before
    any pool is built."""
    _clear_boot_env(monkeypatch)
    main = _load_main()

    async def _no_db_init(*args, **kwargs):
        raise AssertionError("startup must refuse before db.init runs")

    monkeypatch.setattr(main.db, "init", _no_db_init)
    from fastapi.testclient import TestClient

    with pytest.raises(RuntimeError, match="refusing to start"):
        with TestClient(main.app):
            pass  # pragma: no cover — the lifespan must raise


def test_startup_boots_dev_open_with_the_explicit_opt_in(monkeypatch, caplog):
    """P0-1: with the opt-out the app boots — logged as the DEV-OPEN mode it
    is, and unauthenticated calls authenticate as `disabled`."""
    _clear_boot_env(monkeypatch)
    monkeypatch.setenv("MTK_ALLOW_UNAUTHENTICATED", "1")
    main = _load_main()

    seen = {}

    async def _capture_db_init(url):
        seen["url"] = url  # the dev fallback DSN — no database is touched

    monkeypatch.setattr(main.db, "init", _capture_db_init)
    from fastapi.testclient import TestClient

    import logging
    with caplog.at_level(logging.CRITICAL, logger="mtk.api"):
        with TestClient(main.app) as client:
            # /health probes the database; /whoami is the credential-free
            # identity probe and proves the app is actually serving.
            assert client.get("/whoami").json() == {
                "actor": None, "auth": "disabled"}
    assert seen["url"] == main._DEV_DATABASE_URL
    assert [r for r in caplog.records if "DEV-OPEN" in r.getMessage()], (
        "dev-open boot must be named in a CRITICAL banner")


def test_missing_database_url_fails_fast_unless_dev_open(monkeypatch):
    """P2-3: a deployment without DATABASE_URL refuses to bootstrap a pool;
    only the dev-open opt-in keeps the historical local default."""
    _clear_boot_env(monkeypatch)
    main = _load_main()
    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        main.required_database_url()

    monkeypatch.setenv("MTK_ALLOW_UNAUTHENTICATED", "1")
    assert main.required_database_url() == main._DEV_DATABASE_URL

    # A configured deployment URL wins outright (fresh module read):
    monkeypatch.setenv("DATABASE_URL", "postgresql://deployment/db")
    assert _load_main().required_database_url() == "postgresql://deployment/db"


def test_startup_with_credentials_and_a_real_url_needs_no_opt_in(monkeypatch):
    """Production shape: token + DATABASE_URL → boots, quietly (no banner —
    it is not dev-open)."""
    monkeypatch.delenv("MTK_ALLOW_UNAUTHENTICATED", raising=False)
    monkeypatch.setenv("MTK_API_TOKEN", "service-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql://deployment/db")
    main = _load_main()

    seen = {}

    async def _capture_db_init(url):
        seen["url"] = url

    monkeypatch.setattr(main.db, "init", _capture_db_init)
    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        assert client.get("/whoami").status_code == 401  # credentials required
        ok = client.get("/whoami", headers={"Authorization": "Bearer service-token"})
        assert ok.status_code == 200 and ok.json()["auth"] == "service"
    assert seen["url"] == "postgresql://deployment/db"
