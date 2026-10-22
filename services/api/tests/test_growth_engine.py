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


def test_summary_compares_platforms_and_languages():
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
