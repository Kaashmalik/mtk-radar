"""Cache layer (v0.22): the cache is an OPTIMIZATION. Every failure mode —
no redis package, no REDIS_URL, unreachable server, broken payload — must
degrade to "no cache", never to a failed request.
"""

import asyncio
import json

import cache


class FakeRedis:
    def __init__(self, store=None, fail=False):
        self.store = store if store is not None else {}
        self.fail = fail

    async def get(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        if self.fail:
            raise RuntimeError("redis down")
        self.store[key] = value.encode() if isinstance(value, str) else value
        return True


def _reset(monkeypatch, client):
    monkeypatch.setattr(cache, "_client", client)
    monkeypatch.setattr(cache, "_checked", True)
    monkeypatch.setattr(cache, "_disabled", client is None)


def test_without_redis_everything_is_a_miss(monkeypatch):
    _reset(monkeypatch, None)
    assert asyncio.run(cache.cache_get_json("k")) is None
    assert asyncio.run(cache.cache_set_json("k", {"a": 1})) is False


def test_round_trip(monkeypatch):
    fake = FakeRedis()
    _reset(monkeypatch, fake)
    assert asyncio.run(cache.cache_set_json("k", {"a": 1})) is True
    assert asyncio.run(cache.cache_get_json("k")) == {"a": 1}


def test_a_broken_cache_never_raises(monkeypatch):
    _reset(monkeypatch, FakeRedis(fail=True))
    assert asyncio.run(cache.cache_get_json("k")) is None
    assert asyncio.run(cache.cache_set_json("k", {"a": 1})) is False


def test_unparseable_payload_is_a_miss(monkeypatch):
    fake = FakeRedis({"k": b"{not json"})
    _reset(monkeypatch, fake)
    assert asyncio.run(cache.cache_get_json("k")) is None


def test_status_reports_configuration(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    status = cache.cache_status()
    assert status["url_configured"] is True
    monkeypatch.delenv("REDIS_URL")
    assert cache.cache_status()["url_configured"] is False
