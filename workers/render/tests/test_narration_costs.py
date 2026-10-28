"""WP-F cost engine on the TTS path: a re-render of unchanged narration costs
0 characters (shared cache), an exhausted budget degrades to capture audio,
and real character counts land in the ledger."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import narration  # noqa: E402


class FakeCost:
    def __init__(self):
        self.store: dict[str, object] = {}
        self.events: list[dict] = []
        self.budget_call_count = 0
        self.budget_calls: list[dict] = []
        self.allow = True
        self.reservation_id: str | None = None

    def cache_lookup(self, namespace, key):
        return self.store.get(f"{namespace}:{key}")

    def cache_store(self, namespace, key, value, ttl_s=None):
        self.store[f"{namespace}:{key}"] = value

    def budget_ok(self, kind, **kwargs):
        self.budget_call_count += 1
        return self.allow

    def budget_check(self, kind, **kwargs):
        """G04 interface: gate response with a reservation id."""
        self.budget_call_count += 1
        self.budget_calls.append({"kind": kind, **kwargs})
        return {"allowed": self.allow,
                "reason": None if self.allow else "budget exhausted",
                "reservation_id": (self.reservation_id
                                   if self.allow and self.reservation_id else None)}

    def report(self, kind, **kwargs):
        self.events.append({"kind": kind, **kwargs})


def _tts_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TTS_BASE_URL", "https://tts.invalid/v1")
    monkeypatch.setenv("TTS_API_KEY", "k-test")
    monkeypatch.setenv("TTS_MODEL", "tts-1")
    monkeypatch.setenv("TTS_VOICE", "onyx")


def test_rerender_of_unchanged_narration_costs_zero_chars(monkeypatch, tmp_path):
    _tts_env(monkeypatch, tmp_path)
    cost = FakeCost()
    existing = tmp_path / "warm.mp3"
    existing.write_bytes(b"\x00mp3")

    def key(text, **kw):
        import costing
        return costing.tts_cache_key(text, voice=kw["voice"], model=kw["model"])

    import costing
    k = costing.tts_cache_key("Hello walkthrough", voice="onyx", model="tts-1")
    cost.store[f"tts:{k}"] = {"path": str(existing)}

    def no_network(*a, **kw):
        raise AssertionError("a cached narration must not call the provider")

    monkeypatch.setattr(httpx, "post", no_network)
    out = narration.synthesize("Hello walkthrough", tmp_path / "n-000.mp3",
                               cost=cost)
    assert out == existing
    (event,) = cost.events
    assert event["kind"] == "tts" and event["units"] == 0
    assert event["meta"]["cache_hit"] is True


def test_missing_cache_file_falls_through_to_synthesis(monkeypatch, tmp_path):
    _tts_env(monkeypatch, tmp_path)
    cost = FakeCost()
    import costing
    k = costing.tts_cache_key("Hello again", voice="onyx", model="tts-1")
    cost.store[f"tts:{k}"] = {"path": str(tmp_path / "gone.mp3")}  # deleted

    def fake_post(url, **kw):
        class Resp:
            status_code = 200
            content = b"mp3-bytes"

            def raise_for_status(self):
                return None

        return Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    out = narration.synthesize("Hello again", tmp_path / "n-001.mp3", cost=cost)
    assert out is not None and out.exists()
    chars = [e for e in cost.events if e["kind"] == "tts"]
    # one miss → exactly one paid event with the real char count
    paid = [e for e in chars if e["units"] > 0]
    assert len(paid) == 1 and paid[0]["units"] == len("Hello again")


def test_exhausted_tts_budget_degrades_to_capture_audio(monkeypatch, tmp_path):
    _tts_env(monkeypatch, tmp_path)
    cost = FakeCost()
    cost.allow = False

    def no_network(*a, **kw):
        raise AssertionError("a denied budget must not spend")

    monkeypatch.setattr(httpx, "post", no_network)
    out = narration.synthesize("long narration", tmp_path / "n-002.mp3",
                               cost=cost)
    assert out is None, "the pipeline must fall back to capture audio"
    assert cost.budget_call_count == 1


def test_synthesize_all_passes_cost_through(monkeypatch, tmp_path):
    _tts_env(monkeypatch, tmp_path)
    seen = []

    def fake_synth(text, out, *, language="en", cost=None, **kw):
        seen.append(cost)
        out.write_bytes(b"x")
        return out

    monkeypatch.setattr(narration, "synthesize", fake_synth)
    result = narration.synthesize_all(["a", "b"], tmp_path, cost="cost-client")
    assert result["used"] is True and all(c == "cost-client" for c in seen)


# ------------------------------------------------- verified-local TTS (M7)

def test_tts_local_flag_is_honoured_only_for_local_endpoints(monkeypatch):
    from narration import tts_local

    monkeypatch.setenv("TTS_LOCAL", "1")
    for local in ("http://localhost:8880/v1", "http://127.0.0.1:5000/v1",
                  "http://192.168.1.20:8880/v1", "http://kokoro:8880/v1", "http://[::1]:9000/v1"):
        assert tts_local(local), local
    for public in ("https://api.openai.com/v1", "https://tts.example.com/v1",
                   "http://8.8.8.8/v1", ""):
        assert not tts_local(public), public
    monkeypatch.setenv("TTS_LOCAL", "0")
    assert not tts_local("http://localhost:8880/v1")


def test_local_tts_needs_no_key_skips_paid_budget_and_reports_free(monkeypatch, tmp_path):
    import httpx

    import narration

    monkeypatch.setenv("TTS_LOCAL", "1")
    monkeypatch.delenv("TTS_API_KEY", raising=False)
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["url"], seen["headers"] = url, headers
        return httpx.Response(200, content=b"ID3audio", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    class Cost:
        def __init__(self):
            self.reports, self.checked = [], False

        def cache_lookup(self, kind, key):
            return None

        def budget_check(self, *a, **k):
            self.checked = True
            return {"allowed": False}

        def cache_store(self, *a, **k):
            pass

        def report(self, kind, **kw):
            self.reports.append(kw)

    cost = Cost()
    out = narration.synthesize("Hello there.", tmp_path / "n.mp3",
                               base_url="http://localhost:8880/v1", cost=cost)
    assert out is not None and out.read_bytes() == b"ID3audio"
    assert "Authorization" not in seen["headers"], "keyless local server"
    assert cost.checked is False, "a free local server needs no paid reservation"
    assert cost.reports[-1]["provider"] == "local"
    assert cost.reports[-1]["meta"] == {"local": True}


def test_tts_local_on_a_public_endpoint_keeps_the_budget_gate(monkeypatch, tmp_path):
    import narration

    monkeypatch.setenv("TTS_LOCAL", "1")

    class Deny:
        def cache_lookup(self, kind, key):
            return None

        def budget_check(self, *a, **k):
            return {"allowed": False}

    out = narration.synthesize("Hello.", tmp_path / "n.mp3",
                               base_url="https://api.openai.com/v1", api_key="sk-test",
                               cost=Deny())
    assert out is None, "public endpoint → paid path → budget refusal stands"
