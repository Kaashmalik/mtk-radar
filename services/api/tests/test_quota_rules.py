"""YouTube quota day/limit rules (Q1) — pure functions, no database."""

from datetime import date, datetime, timezone

from quota_api import daily_limit, decide, quota_day, resets_at


def test_quota_day_is_pacific_and_flips_at_pacific_midnight():
    # 07:59 UTC on 28 Oct (PDT, UTC-7) is still 27 Oct in California.
    assert quota_day(datetime(2026, 10, 28, 6, 59, tzinfo=timezone.utc)) == date(2026, 10, 27)
    assert quota_day(datetime(2026, 10, 28, 7, 0, tzinfo=timezone.utc)) == date(2026, 10, 28)


def test_reset_instant_follows_daylight_saving():
    assert resets_at(date(2026, 10, 28)).isoformat() == "2026-10-29T07:00:00+00:00"  # PDT
    assert resets_at(date(2026, 11, 5)).isoformat() == "2026-11-06T08:00:00+00:00"   # PST


def test_decide_never_plans_past_the_limit():
    assert decide(used=8000, requested=2000, limit=10_000) == (True, 0)
    assert decide(used=8500, requested=2000, limit=10_000) == (False, 1500)
    assert decide(used=10_500, requested=1, limit=10_000) == (False, 0)
    assert decide(used=999_999, requested=5, limit=0) == (True, 0), "0 = unmetered bucket"


def test_limits_come_from_env_with_conservative_defaults(monkeypatch):
    monkeypatch.delenv("YOUTUBE_QUOTA_UNITS_PER_DAY", raising=False)
    assert daily_limit("youtube", "units") == 10_000
    monkeypatch.setenv("YOUTUBE_QUOTA_UNITS_PER_DAY", "50000")
    assert daily_limit("youtube", "units") == 50_000
    monkeypatch.setenv("YOUTUBE_QUOTA_UNITS_PER_DAY", "bad")
    assert daily_limit("youtube", "units") == 10_000
    assert daily_limit("youtube", "nope") is None and daily_limit("tiktok", "units") is None
