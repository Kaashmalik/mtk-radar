"""Per-account circuit breaker (EP-07) — pure, injected clock."""

from circuit import AccountBreaker


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_opens_after_threshold_and_isolates_accounts():
    clock = Clock()
    breaker = AccountBreaker(threshold=3, cooldown_s=60, clock=clock)
    bad, good = AccountBreaker.key("youtube", "a"), AccountBreaker.key("youtube", "b")
    assert breaker.failure(bad) is False and breaker.failure(bad) is False
    assert breaker.failure(bad) is True
    assert breaker.allow(bad)[0] is False
    assert breaker.allow(good) == (True, 0.0), "another account is unaffected"


def test_half_open_allows_exactly_one_probe():
    clock = Clock()
    breaker = AccountBreaker(threshold=1, cooldown_s=60, clock=clock)
    key = AccountBreaker.key("facebook", "page")
    breaker.failure(key)
    clock.t += 61
    assert breaker.allow(key)[0] is True
    assert breaker.allow(key)[0] is False, "second caller waits for the probe"
    breaker.failure(key)  # probe failed → re-open for a full cooldown
    assert breaker.allow(key)[0] is False
    clock.t += 61
    assert breaker.allow(key)[0] is True
    breaker.success(key)
    assert breaker.allow(key) == (True, 0.0) and not breaker.is_open(key)


def test_success_resets_the_failure_count():
    breaker = AccountBreaker(threshold=2, cooldown_s=60, clock=Clock())
    key = AccountBreaker.key("tiktok", None)
    breaker.failure(key)
    breaker.success(key)
    assert breaker.failure(key) is False, "count restarted after success"


def test_retry_after_holds_the_breaker_open_longer():
    clock = Clock()
    breaker = AccountBreaker(threshold=1, cooldown_s=60, clock=clock)
    key = AccountBreaker.key("youtube", "a")
    breaker.failure(key, min_open_s=600)
    clock.t += 300
    allowed, remaining = breaker.allow(key)
    assert allowed is False and 290 <= remaining <= 300


def test_env_config_and_bad_values_fall_back(monkeypatch):
    monkeypatch.setenv("MTK_PUBLISH_BREAKER_THRESHOLD", "5")
    monkeypatch.setenv("MTK_PUBLISH_BREAKER_COOLDOWN_S", "nope")
    breaker = AccountBreaker.from_env()
    assert breaker.threshold == 5 and breaker.cooldown_s == 900.0
