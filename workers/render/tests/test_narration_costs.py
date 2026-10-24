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
