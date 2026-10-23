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
