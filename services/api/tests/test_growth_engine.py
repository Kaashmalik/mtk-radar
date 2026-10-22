"""Closed-loop growth analysis tests."""

from growth_engine import engagement_rate, growth_score, recommendations, summarize


ROWS = [
    {"platform": "youtube", "language": "en", "views": 10_000, "likes": 500,
     "comments": 50, "impressions": 20_000, "retention_3s": 0.62, "link_clicks": 80},
    {"platform": "youtube", "language": "en", "views": 5_000, "likes": 200,
     "comments": 20, "impressions": 10_000, "retention_3s": 0.51, "link_clicks": 40},
    {"platform": "tiktok", "language": "ur", "views": 2_000, "likes": 100,
     "comments": 10, "impressions": 4_000, "retention_3s": 0.30, "link_clicks": 5},
]


def test_engagement_rate_is_zero_safe():
    assert engagement_rate(0, 10, 2) == 0.0
    assert engagement_rate(100, 5, 5) == 10.0


def test_growth_score_is_bounded_and_rewards_strong_rows():
    assert growth_score([]) == 0.0
    score = growth_score(ROWS)
    assert 0 < score <= 100
    weak = growth_score([{"views": 10, "likes": 0, "comments": 0}])
    assert score > weak


def test_growth_score_counts_a_measured_zero_engagement():
    """High reach with no engagement is not a missing signal.

    The old blend dropped score-0 signals during renormalization, so 10,000
    views and zero likes could still score 100/100. A reported zero must carry
    its weight instead of disappearing.
    """
    silent = growth_score([{"views": 10_000, "likes": 0, "comments": 0}])
    engaged = growth_score([{"views": 10_000, "likes": 500, "comments": 50}])
    assert silent < 80, "zero engagement must reduce the blended score"
    assert engaged > silent


def test_summary_compares_platforms_and_languages(monkeypatch):
    monkeypatch.delenv("MTK_ENABLE_GROWTH_SCORE", raising=False)
    summary = summarize(
        ROWS,
        languages=[
            {"language": "en", "posts": 2, "views": 15_000, "avg_views": 7_500},
            {"language": "ur", "posts": 1, "views": 2_000, "avg_views": 2_000},
        ],
    )
    assert summary["measured_posts"] == 3
    assert summary["by_platform"][0]["platform"] == "youtube"
    assert summary["by_platform"][0]["posts"] == 2
    assert any("youtube" in rec["title"] for rec in summary["recommendations"])
    # Compliance default: measured data stays, the composite blend is absent.
    assert summary["score_enabled"] is False
    assert summary["score"] is None
    assert "compliance review" in summary["score_label"]


def test_composite_score_is_opt_in_after_compliance_review(monkeypatch):
    monkeypatch.setenv("MTK_ENABLE_GROWTH_SCORE", "1")
    summary = summarize(ROWS)
    assert summary["score_enabled"] is True
    assert isinstance(summary["score"], float) and 0 < summary["score"] <= 100


def test_language_recommendation_uses_avg_views_not_missing_views():
    recs = recommendations(
        ROWS,
        languages=[
            {"language": "en", "avg_views": 7_500},
            {"language": "ur", "avg_views": 2_000},
        ],
    )
    assert any(rec["metric"] == "language" and "en" in rec["title"] for rec in recs)


def test_empty_state_recommends_measurement_not_invention():
    recs = recommendations([])
    assert recs[0]["metric"] == "measurement"
    assert "Publish" in recs[0]["title"]


def test_retention_seconds_are_not_silently_treated_as_a_percentage():
    """45 seconds must not score like 45% 3-second retention."""
    seconds_only = growth_score([
        {"views": 1_000, "retention_3s": None, "avg_view_duration_s": 45},
    ])
    measured_retention = growth_score([
        {"views": 1_000, "retention_3s": 0.45},
    ])
    unavailable = growth_score([{"views": 1_000}])

    assert seconds_only == unavailable, "seconds-only data is not retention"
    assert measured_retention > seconds_only


def test_measured_zero_retention_lowers_the_score():
    zero = growth_score([{"views": 1_000, "likes": 10, "retention_3s": 0.0}])
    unavailable = growth_score([{"views": 1_000, "likes": 10}])
    assert zero < unavailable


def test_average_view_percentage_is_a_valid_retention_fraction():
    from_percentage = growth_score([
        {"views": 1_000, "avg_view_percentage": 0.45},
    ])
    from_retention = growth_score([
        {"views": 1_000, "retention_3s": 0.45},
    ])
    assert from_percentage == from_retention


def test_two_posts_do_not_produce_a_platform_winner():
    recs = recommendations(ROWS[:2])
    assert not any(rec["metric"] == "reach" for rec in recs)


def test_one_language_does_not_produce_a_language_winner():
    recs = recommendations(
        [{"platform": "youtube", "language": "en", "views": 100}],
        languages=[{"language": "en", "avg_views": 100}],
    )
    assert not any(rec["metric"] == "language" for rec in recs)


def test_unknown_views_do_not_produce_engagement_advice():
    recs = recommendations([
        {"platform": "youtube", "language": "en", "views": None,
         "impressions": 1_000, "likes": 50},
    ])
    assert not any(rec["metric"] == "engagement" for rec in recs)


def test_zero_platform_views_are_not_a_winner():
    recs = recommendations([
        {"platform": "youtube", "views": 0, "impressions": 1_000},
        {"platform": "tiktok", "views": 0, "impressions": 500},
        {"platform": "facebook", "views": 0, "impressions": 100},
    ])
    assert not any("leads this small measured set" in rec["detail"] for rec in recs)
