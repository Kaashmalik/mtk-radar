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


# ------------------------------------- 2026 playbook: 3-competitor rule

def comp(**kw):
    base = {"channel": "Mid A", "subscribers": 42_000, "views_28d": 91_000}
    base.update(kw)
    return base


def test_three_competitor_rule_bumps_demand_only_with_a_real_sample():
    from trend_engine import competitor_evidence, score_item

    # A low-demand lead so the demand bump is visible (demands cap at 100).
    low = item(title="Quarterly partner report", url="https://provider.example/q3",
               text="partner program notes")
    base = score_item(low, now=NOW)
    # Three in-band channels, all outsizing their subscriber count -> trending.
    hot = score_item(low, now=NOW, competitors=[
        comp(), comp(channel="Mid B", subscribers=51_000, views_28d=110_000),
        comp(channel="Mid C", subscribers=88_000, views_28d=120_000),
    ])
    assert hot["score"] > base["score"]
    evidence = hot["signals"]["competitor_evidence"]
    assert evidence["in_band"] == 3 and evidence["demand_hits"] == 3
    assert evidence["sample_ok"] is True
    assert hot["score"] - base["score"] <= 20 * 0.28 + 0.01, "bump is bounded"
    assert any("3-competitor rule" in d for d in hot["score_reason"]["why_now"])

    # Two channels are not a sample — no bump, and the risk says why.
    thin = score_item(low, now=NOW, competitors=[comp(), comp(channel="Mid B")])
    assert thin["signals"]["competitor_evidence"]["sample_ok"] is False
    assert any("competitor sample is thin" in r for r in thin["score_reason"]["risks"])

    # A big in-band sample that does NOT out-perform is a demand warning.
    flat = score_item(low, now=NOW, competitors=[
        comp(views_28d=9_000), comp(channel="B", subscribers=50_000, views_28d=10_000),
        comp(channel="C", subscribers=60_000, views_28d=20_000),
    ])
    assert flat["score"] <= base["score"] + 0.01
    assert any("demand unproven" in r for r in flat["score_reason"]["risks"])
    assert competitor_evidence([comp(subscribers=500)])["in_band"] == 0


def test_apply_competitor_evidence_rescores_a_stored_candidate():
    from trend_engine import apply_competitor_evidence, score_item

    stored = score_item(item(title="Quarterly partner report",
                             url="https://provider.example/q3",
                             text="partner program notes"), now=NOW)
    rescored = apply_competitor_evidence(stored, [
        comp(), comp(channel="Mid B", subscribers=51_000, views_28d=110_000),
        comp(channel="Mid C", subscribers=88_000, views_28d=120_000),
    ])
    direct = score_item(item(title="Quarterly partner report",
                             url="https://provider.example/q3",
                             text="partner program notes"), now=NOW, competitors=[
        comp(), comp(channel="Mid B", subscribers=51_000, views_28d=110_000),
        comp(channel="Mid C", subscribers=88_000, views_28d=120_000),
    ])
    assert rescored["score"] == direct["score"], "path-independent: same weights"
    assert rescored["demand_score"] == direct["demand_score"]
    assert "3-competitor rule" in " ".join(rescored["score_reason"]["why_now"])

    # Idempotent re-application must not compound the bump.
    again = apply_competitor_evidence(rescored, [comp()])
    assert again["score"] == rescored["score"] or again["score"] <= rescored["score"]


# ------------------------------------------- velocity + corroboration (WP-B)

def test_smooth_velocity_guards_and_ema():
    from trend_engine import smooth_velocity

    # Before the first reliable gap the stored velocity is kept.
    prev_obs = NOW - timedelta(minutes=20)
    assert smooth_velocity(50, 80, prev_obs, NOW, prev_velocity=1.5) == 1.5

    # A fresh sample after >1h produces the instant rate, smoothed with the
    # previous velocity.
    prev_obs = NOW - timedelta(hours=4)
    # 50 -> 80 in 4h = +7.5/h; EMA(1.5, 7.5) = 0.6*1.5 + 0.4*7.5 = 3.9
    assert smooth_velocity(50, 80, prev_obs, NOW, prev_velocity=1.5) == 3.9

    # Without a previous velocity the instant rate is used directly.
    assert smooth_velocity(50, 80, prev_obs, NOW, prev_velocity=0) == 7.5

    # Past the stale window the instant rate alone survives.
    stale_obs = NOW - timedelta(hours=72)
    assert smooth_velocity(50, 65, stale_obs, NOW, prev_velocity=9.9) == \
        round(15 / 72, 3)

    # No previous observation at all → unchanged.
    assert smooth_velocity(None, 80, None, NOW, prev_velocity=2.0) == 2.0

    # Falling scores produce honest negative velocity.
    assert smooth_velocity(80, 40, prev_obs, NOW, prev_velocity=1.0) == \
        round(0.6 * 1.0 + 0.4 * (-40 / 4), 3)


def test_velocity_and_corroboration_bump_demand_with_caps():
    from trend_engine import corroboration_bump, velocity_bump

    # Bounded, explainable bumps.
    assert velocity_bump(3.0) == 12.0
    assert velocity_bump(10.0) == 15.0   # capped
    assert velocity_bump(-2.0) == 0.0    # cooling never adds demand
    assert velocity_bump(0) == 0.0

    assert corroboration_bump(1) == 0.0  # a single source is not corroboration
    assert corroboration_bump(3) == 6.0
    assert corroboration_bump(9) == 10.0  # capped

    # Demand is capped at 100, so the bump must be visible on a COLD item.
    cold = dict(item(title="A page", url="https://example.com/x",
                     source_category=None, trust_tier=None, country_scope=[],
                     text=""))
    base = score_item(cold, now=NOW)
    rising = score_item(cold, now=NOW, velocity=4.0, corroborating_sources=3)
    assert rising["score"] > base["score"]
    assert rising["demand_score"] == min(
        100.0, base["demand_score"] + velocity_bump(4.0) + corroboration_bump(3))
    assert any("rising on the radar" in d for d in rising["score_reason"]["why_now"])
    assert any("independent sources" in d for d in rising["score_reason"]["why_now"])
    assert rising["signals"]["velocity"] == 4.0
    assert rising["signals"]["corroborating_sources"] == 3


def test_cooling_story_records_a_risk_not_a_bonus():
    falling = score_item(item(), now=NOW, velocity=-3.0)
    base = score_item(item(), now=NOW)
    assert falling["score"] == base["score"]  # no demand change
    assert any("momentum is fading" in r for r in falling["score_reason"]["risks"])


def test_research_papers_and_trend_signal_categories_score_deliberately():
    paper = score_item(item(source_category="research_papers"), now=NOW)
    signal = score_item(item(source_category="trend_signals"), now=NOW)
    unknown = score_item(item(source_category="mystery_box"), now=NOW)
    assert paper["audience_fit"] > unknown["audience_fit"]
    assert signal["audience_fit"] >= unknown["audience_fit"]
