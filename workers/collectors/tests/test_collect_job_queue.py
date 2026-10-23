"""Durable collect-job drain (v0.33): the collector claims recurring
`collect` jobs (source creation enqueues one; each poll-result re-arms it
with the source's cadence) instead of relying only on the in-memory cadence
sweep. The sweep stays the fail-open fallback; a queue outage never stops
collection, and a disabled/removed source resolves its job as done.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "mtk_collector_main", Path(__file__).resolve().parent.parent / "main.py")
col = importlib.util.module_from_spec(_spec)
sys.modules["mtk_collector_main"] = col
_spec.loader.exec_module(col)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise col.httpx.HTTPStatusError("error", request=None, response=None)


SOURCE = {"id": "src-1", "provider": "Acme Domains", "adapter": "manual",
          "polling_cadence": "6 hours", "config": {}, "enabled": True}


class FakeClient:
    def __init__(self, sources, claims):
        self.sources = sources
        self.claims = list(claims)
        self.posts = []

    def get(self, path, params=None):
        if path.endswith("/automation/policy"):
            return FakeResponse({"policy": {"stages": {"collect": "auto"}}})
        return FakeResponse(self.sources)

    def post(self, path, json=None):  # noqa: A002
        self.posts.append((path, json))
        if path.endswith("/jobs/claim"):
            return FakeResponse(self.claims.pop(0) if self.claims
                                else {"claimed": False})
        if path.endswith("/poll-result"):
            return FakeResponse({"ok": json.get("ok") if json else True})
        if path.endswith("/result"):
            return FakeResponse({"id": path.split("/")[2], "status": "done"})
        return FakeResponse({"ok": True})


def _collector(client):
    c = col.Collector(api_url="http://fake")
    c.client = client
    return c


def test_claimed_collect_job_polls_its_source(monkeypatch):
    client = FakeClient([SOURCE], [
        {"claimed": True, "id": "job-1", "kind": "collect",
         "entity_id": "src-1", "payload": {}, "attempt": 1}])
    monkeypatch.setattr(col, "collect", lambda source, fetcher: [])
    c = _collector(client)
    asyncio.run(c.sweep())
    poll_results = [j for p, j in client.posts if p.endswith("/poll-result")]
    assert poll_results, "the claimed job must drive a real poll"
    # recurring contract: success is reported via poll-result (re-arm),
    # NOT via a terminal job result
    assert not [p for p, _ in client.posts if p.endswith("/result")]


def test_disabled_source_resolves_job_without_polling(monkeypatch):
    client = FakeClient([], [  # enabled list does not contain the claimed source
        {"claimed": True, "id": "job-1", "kind": "collect",
         "entity_id": "src-disabled", "payload": {}, "attempt": 1}])
    monkeypatch.setattr(col, "collect", lambda source, fetcher: [])
    c = _collector(client)
    asyncio.run(c.sweep())
    done = [(p, j) for p, j in client.posts if p.endswith("/result")]
    assert done and done[0][1]["ok"] is True and "disabled" in done[0][1]["detail"]
    assert not [p for p, _ in client.posts if p.endswith("/poll-result")]


def test_failed_poll_reports_failure_not_job_result(monkeypatch):
    client = FakeClient([SOURCE], [
        {"claimed": True, "id": "job-1", "kind": "collect",
         "entity_id": "src-1", "payload": {}, "attempt": 1}])

    def boom(source, fetcher):
        raise RuntimeError("adapter exploded")

    monkeypatch.setattr(col, "collect", boom)
    c = _collector(client)
    asyncio.run(c.sweep())
    failed = [(p, j) for p, j in client.posts if p.endswith("/poll-result")]
    assert failed and failed[0][1]["ok"] is False
    # the failed poll-result re-arms the job (API side); the worker itself
    # must not file a terminal result for a live source
    assert not [p for p, _ in client.posts if p.endswith("/result")]


def test_queue_unreachable_degrades_to_cadence_sweep(monkeypatch):
    class DeadClient(FakeClient):
        def post(self, path, json=None):  # noqa: A002
            self.posts.append((path, json))
            if path.endswith("/jobs/claim"):
                raise col.httpx.ConnectError("down")
            return FakeResponse({"ok": True})

    client = DeadClient([SOURCE], [])
    monkeypatch.setattr(col, "collect", lambda source, fetcher: [])
    c = _collector(client)
    asyncio.run(c.sweep())  # must not raise; falls back to the cadence loop
    polys = [p for p, _ in client.posts if p.endswith("/poll-result")]
    assert polys, "the cadence sweep must still poll every due source"


def test_knob_disables_the_drain(monkeypatch):
    monkeypatch.setenv("MTK_COLLECT_JOB_QUEUE", "0")
    client = FakeClient([SOURCE], [])
    c = _collector(client)
    assert asyncio.run(c._drain_collect_jobs([SOURCE])) == 0
    assert not [p for p, _ in client.posts if p.endswith("/jobs/claim")]
