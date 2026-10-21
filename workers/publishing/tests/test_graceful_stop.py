"""Graceful shutdown (v0.20): SIGTERM (docker stop, systemd) must not
abandon a post mid-upload — the worker finishes the item it is on, then
stops. The flag is checked BETWEEN posts, never in the middle of one.
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "mtk_publishing_main", Path(__file__).resolve().parent.parent / "main.py")
pub = importlib.util.module_from_spec(_spec)
sys.modules["mtk_publishing_main"] = pub
_spec.loader.exec_module(pub)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAPI:
    def __init__(self, posts):
        self.posts = posts
        self.published = []

    def get(self, path, params=None):
        if path == "/schedules":
            return FakeResponse(self.posts)
        return FakeResponse([])

    def post(self, path, json=None):
        self.published.append((path, json))
        return FakeResponse({"ok": True})


def _post(idx):
    return {"id": f"sch-{idx}", "platform": "youtube", "local_time": "2020-01-01T00:00:00+00:00",
            "offer_id": f"off-{idx}", "metadata": {}, "privacy": "private",
            "idempotency_key": f"k-{idx}"}


def test_stop_flag_stops_the_sweep_between_posts(monkeypatch):
    """The first post is published, then the stop flag is honoured: the
    remaining posts are left for the next run instead of being abandoned."""
    posts = [_post(i) for i in range(3)]
    api = FakeAPI(posts)
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api

    def fake_publish(post, adapters):
        api.published.append(("publish", post["id"]))
        if post["id"] == "sch-0":
            pub._STOP = True  # stop requested right after the first post

    monkeypatch.setattr(worker, "_publish", fake_publish)
    monkeypatch.setattr(worker, "build_adapters", lambda: {})
    monkeypatch.setattr(worker, "retry_failed", lambda now=None: 0)
    monkeypatch.setattr(worker, "apply_corrections", lambda adapters: 0)
    monkeypatch.setattr(pub, "_STOP", False)

    worker.run_once()

    published = [p for p in api.published if p[0] == "publish"]
    assert [p[1] for p in published] == ["sch-0"], \
        "the sweep must stop after the item in flight, not abandon the rest mid-way"
    assert pub._STOP is True


def test_signal_handler_sets_the_stop_flag(monkeypatch):
    """SIGTERM/SIGINT must flip the flag the loops watch."""
    captured = {}

    def fake_signal(sig, handler):
        captured[sig] = handler

    monkeypatch.setattr(pub.signal, "signal", fake_signal)
    monkeypatch.setattr(pub, "_STOP", False)

    pub._install_stop_handlers()
    assert set(captured) == {pub.signal.SIGTERM, pub.signal.SIGINT}

    captured[pub.signal.SIGTERM](pub.signal.SIGTERM, None)
    assert pub._STOP is True
