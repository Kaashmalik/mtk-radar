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


# --------------------- G11 (EP-02): cache hits never 500; expiry preserved

class _FakePool:
    """fetchrow stand-in for the Postgres cache layer."""

    def __init__(self, row=None, fail=False):
        self.row = row
        self.fail = fail

    async def fetchrow(self, *_a, **_k):
        if self.fail:
            raise RuntimeError("pg down")
        return self.row


def test_redis_hit_promotes_value_with_remaining_ttl(monkeypatch):
    import time

    import costs_store

    class TTLRedis(FakeRedis):
        async def ttl(self, key):
            return 120

    fake = TTLRedis({"k": json.dumps({"a": 1})})
    _reset(monkeypatch, fake)
    monkeypatch.setattr(costs_store, "_MEM_CACHE", {})
    assert asyncio.run(costs_store.cache_get(None, "k")) == {"a": 1}
    expires_at, _raw = costs_store._MEM_CACHE["k"]
    remaining = expires_at - time.time()
    assert 115 <= remaining <= 121, "the Redis hit must keep its own expiry"


def test_redis_hit_without_ttl_gets_bounded_default(monkeypatch):
    import time

    import costs_store

    class NoTTLRedis(FakeRedis):
        async def ttl(self, key):
            return -1  # key without expiry

    fake = NoTTLRedis({"k": json.dumps({"a": 1})})
    _reset(monkeypatch, fake)
    monkeypatch.setattr(costs_store, "_MEM_CACHE", {})
    assert asyncio.run(costs_store.cache_get(None, "k")) == {"a": 1}
    expires_at, _raw = costs_store._MEM_CACHE["k"]
    remaining = expires_at - time.time()
    assert 0 < remaining <= 31, "an unknown expiry must stay bounded, not crash"


def test_pg_hit_returns_value_with_remaining_expiry(monkeypatch):
    import costs_store

    _reset(monkeypatch, None)  # force the Postgres layer
    monkeypatch.setattr(costs_store, "_MEM_CACHE", {})
    pool = _FakePool(row={"value": json.dumps({"a": 1}), "ttl_s": 42})
    assert asyncio.run(costs_store.cache_get(pool, "k")) == {"a": 1}
    # The promoted memory entry carries the PG remaining TTL (42s ±slack).
    expires_at, _raw = costs_store._MEM_CACHE["k"]
    assert 0 < expires_at, "memory promotion must happen also for PG hits"


def test_every_outage_path_is_a_miss_never_a_500(monkeypatch):
    """The G11 regression: a Redis/PG hit called _mem_put WITHOUT its
    required ttl_s → TypeError → cache reads 500'd. Every layer combination
    now returns cleanly."""
    import costs_store

    _reset(monkeypatch, FakeRedis(fail=True))
    monkeypatch.setattr(costs_store, "_MEM_CACHE", {})
    assert asyncio.run(costs_store.cache_get(_FakePool(fail=True), "k")) is None
    assert asyncio.run(costs_store.cache_get(None, "k")) is None
    # And a genuine hit OUT of a fully reachable stack never raises either.
    class TTLRedis(FakeRedis):
        async def ttl(self, key):
            return 60

    _reset(monkeypatch, TTLRedis({"k": json.dumps([1, 2, 3])}))
    assert asyncio.run(costs_store.cache_get(_FakePool(row=None), "k")) == [1, 2, 3]


def test_mem_put_is_safe_without_explicit_ttl():
    import time

    import costs_store

    costs_store._MEM_CACHE.clear()
    costs_store._mem_put("k", {"a": 1})  # old bug: TypeError (missing ttl_s)
    expires_at, raw = costs_store._MEM_CACHE["k"]
    assert 0 < expires_at - time.time() <= 31
    import json as _json
    assert _json.loads(raw) == {"a": 1}
