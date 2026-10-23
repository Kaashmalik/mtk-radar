"""CORS allowlist (v0.20): the dashboard's client-side islands run in the
browser, so the browser enforces CORS. A hardcoded localhost-only allowlist
silently breaks every interactive action in any real deployment (127.0.0.1,
a domain, a reverse proxy) — the origin list must follow the deployment.
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_spec = importlib.util.spec_from_file_location(
    "api_main_cors", Path(__file__).resolve().parents[1] / "main.py")
api_main = importlib.util.module_from_spec(_spec)
sys.modules["api_main_cors"] = api_main
_spec.loader.exec_module(api_main)


def test_local_dashboard_origins_are_allowed_by_default(monkeypatch):
    monkeypatch.delenv("MTK_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("MTK_PUBLIC_BASE_URL", raising=False)
    origins = api_main._cors_origins()
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


def test_configured_origins_are_allowed(monkeypatch):
    monkeypatch.setenv("MTK_CORS_ORIGINS", "https://radar.example.com, https://desk.example.com")
    monkeypatch.delenv("MTK_PUBLIC_BASE_URL", raising=False)
    origins = api_main._cors_origins()
    assert "https://radar.example.com" in origins
    assert "https://desk.example.com" in origins


def test_public_base_url_is_allowed_automatically(monkeypatch):
    monkeypatch.delenv("MTK_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("MTK_PUBLIC_BASE_URL", "https://radar.example.com/")
    origins = api_main._cors_origins()
    assert "https://radar.example.com" in origins, "trailing slash must be normalized"


def test_origins_are_deduplicated_and_normalized(monkeypatch):
    monkeypatch.setenv("MTK_CORS_ORIGINS", "https://a.example.com/,https://b.example.com")
    monkeypatch.setenv("MTK_PUBLIC_BASE_URL", "https://a.example.com")
    origins = api_main._cors_origins()
    assert origins.count("https://a.example.com") == 1
    assert "https://a.example.com/" not in origins

def test_localhost_fallback_applies_only_when_nothing_is_configured(monkeypatch):
    """Once an operator configures ANY origin, localhost is not silently kept
    alongside it: with allow_credentials=True a leftover dev origin on a
    deployed host is a real cross-origin exposure."""
    monkeypatch.setenv("MTK_CORS_ORIGINS", "https://radar.example.com")
    monkeypatch.delenv("MTK_PUBLIC_BASE_URL", raising=False)
    origins = api_main._cors_origins()
    assert origins == ["https://radar.example.com"]
    assert "http://localhost:3000" not in origins
