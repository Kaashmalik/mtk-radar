"""Trend scoring tests — deterministic, explainable, bounded."""

from datetime import datetime, timedelta, timezone

from trend_engine import radar_bands, score_item


NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def item(**overrides):
    base = {
        "id": "11111111-1111-1111-1111-111111111111",
        "title": "Free student cloud credits and domain offer",
        "url": "https://provider.example/students",
        "published_at": (NOW - timedelta(hours=2)).isoformat(),
        "source_provider": "Provider",
        "source_category": "student_programs",
        "trust_tier": "A_provider_owned",
        "country_scope": ["PK"],
        "text": "free credits for students, redeem with eligibility",
    }
    base.update(overrides)
    return base


def test_fresh_provider_lead_scores_above_stale_generic_one():
    fresh = score_item(item(), now=NOW)
    stale = score_item(
        item(title="A page", url="https://example.com/x",
             published_at=(NOW - timedelta(days=90)).isoformat(),
             source_category=None, trust_tier="B_discovery_lead",
             country_scope=[], text=""),
        now=NOW,
    )
    assert fresh["score"] > stale["score"]
    assert fresh["freshness_score"] > stale["freshness_score"]
    assert 0 <= fresh["score"] <= 100


def test_every_component_is_exposed_with_reasons_and_risks():
    scored = score_item(item(), now=NOW)
    for key in ("demand_score", "freshness_score", "feasibility_score",
                "competition_gap", "audience_fit", "monetization"):
        assert isinstance(scored[key], (int, float))
    reason = scored["score_reason"]
    assert reason["why_now"]
    assert "keywords" in reason and "risks" in reason
    assert scored["signals"]["keyword_hits"]


def test_provider_owned_source_is_more_feasible_than_unknown():
    official = score_item(item(), now=NOW)
    unknown = score_item(item(trust_tier=None), now=NOW)
    assert official["feasibility_score"] > unknown["feasibility_score"]


def test_radar_bands_partition_every_candidate():
    candidates = [{"score": score} for score in (90, 70, 50, 20)]
    bands = radar_bands(candidates)
    assert [c["score"] for c in bands["hot"]] == [90]
    assert [c["score"] for c in bands["warm"]] == [70]
    assert [c["score"] for c in bands["watch"]] == [50]
    assert [c["score"] for c in bands["cold"]] == [20]
