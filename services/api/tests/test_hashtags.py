"""WP-E hashtag & packaging engine: documented 2026 platform limits, dedup,
casing, placement, evidence traceability, feedback rollup and gate reasons."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hashtags import (  # noqa: E402
    CAPABILITIES,
    FORBIDDEN_TAGS,
    capability,
    generate_hashtags,
    hashtag_gate_problems,
    hashtagify,
    parse_hashtags,
)
import seo  # noqa: E402

OFFER = {
    "id": "offer-1",
    "title": "One-year .tech domain",
    "provider": "Example Registrar",
    "category": "domains_hosting",
    "eligibility": {"countries": ["Pakistan"]},
}


# ------------------------------------------------------------- capability table


def test_capability_table_matches_the_2026_documented_limits():
    assert CAPABILITIES["youtube"]["hashtag_max"] == 5
    assert CAPABILITIES["youtube"]["placement"] == "description_tail"
    assert CAPABILITIES["youtube"]["backend_tags"] == (5, 8)
    for platform in ("tiktok", "instagram"):
        assert 3 <= CAPABILITIES[platform]["hashtag_min"] <= CAPABILITIES[platform]["hashtag_max"] <= 5
    assert CAPABILITIES["facebook"]["hashtag_min"] == 0
    assert CAPABILITIES["facebook"]["hashtag_max"] == 2


def test_unknown_platform_falls_back_strict():
    assert capability("vtok")["hashtag_max"] <= 2


# -------------------------------------------------------------- traceability


def test_every_tag_cites_a_source_and_nothing_is_invented():
    items = generate_hashtags(
        "instagram",
        provider="Example Registrar",
        category="domains_hosting",
        countries=["Pakistan"],
        trend_keywords=["ai domains"],
    )
    assert items
    for item in items:
        assert set(item) == {"tag", "source", "ref"}
        assert item["source"] in {"trend", "category", "provider", "eligibility"}
        assert item["ref"]  # human-readable provenance


def test_trend_tags_only_enter_through_the_trend_row():
    without = {i["tag"] for i in generate_hashtags("instagram", provider="", category="")}
    with_trend = generate_hashtags("instagram", provider="", category="",
                                   trend_keywords=["k2 syntax"])
    assert not any("k2" in t.lower() for t in without)
    assert any(t["tag"] == "#K2Syntax" and t["source"] == "trend" for t in with_trend)


def test_vanity_tags_are_never_proposed():
    items = generate_hashtags("tiktok", provider="x", category="ai_tools",
                              trend_keywords=["viral", "fyp"])
    proposed = {i["tag"].lower() for i in items}
    assert proposed.isdisjoint(FORBIDDEN_TAGS)


# ------------------------------------------------------- limits / dedup / casing


def test_platform_limits_are_enforced_in_generation():
    trends = ["tag one", "tag two", "tag three", "tag four", "tag five", "tag six"]
    yt = generate_hashtags("youtube", provider="Acme", category="domains_hosting",
                           countries=["PK"], trend_keywords=trends)
    fb = generate_hashtags("facebook", provider="Acme", category="domains_hosting",
                           countries=["PK"], trend_keywords=trends)
    assert 3 <= len(yt) <= 5          # youtube: 3–5
    assert len(fb) <= 2               # facebook: 0–2


def test_dedup_is_case_insensitive_and_casing_is_camel():
    items = generate_hashtags("instagram", provider="example registrar",
                              category="domains_hosting",
                              trend_keywords=["Example Registrar"])
    tags = [i["tag"] for i in items]
    assert len(tags) == len({t.lower() for t in tags})
    assert all(t == "#" + "".join(word[:1].upper() + word[1:]
                                  for word in t[1:].split("_")) or t[1:].replace("_", "").isalnum()
               for t in tags)


# ------------------------------------------------------------- feedback rollup


def test_measured_lift_is_permission_gated_and_applies_when_enabled(monkeypatch):
    """G21 (evidence-to-video plan): reordering generation from the
    `hashtag_performance` rollup is the same derived-aggregate class as the
    growth-score blend — OFF by default, applied only under the explicit
    MTK_ENABLE_DERIVED_ENGAGEMENT opt-in."""
    trends = ["tag one", "tag two", "tag three"]
    perf = {
        "#TagOne": {"posts": 10, "avg_impressions": 5000.0},
        "#TagTwo": {"posts": 10, "avg_impressions": 20.0},
    }

    # default: performance is IGNORED — source-priority order (trend order)
    # decides; generation with performance data is byte-identical to
    # generation without it.
    monkeypatch.delenv("MTK_ENABLE_DERIVED_ENGAGEMENT", raising=False)
    baseline = generate_hashtags("instagram", provider="Acme", category="",
                                 trend_keywords=trends)
    gated = generate_hashtags("instagram", provider="Acme", category="",
                              trend_keywords=trends, performance=perf)
    assert baseline == gated, \
        "measured lift must NOT reshape generation when the permission is off"

    # opt-in: measured-best leads; the proven underperformer sinks below the
    # unmeasured tag, and facebook's 2-tag cap keeps the winner only.
    monkeypatch.setenv("MTK_ENABLE_DERIVED_ENGAGEMENT", "1")
    items = generate_hashtags("instagram", provider="Acme", category="",
                              trend_keywords=trends, performance=perf)
    tags = [i["tag"] for i in items]
    assert tags.index("#TagOne") < tags.index("#TagTwo")
    fb = generate_hashtags("facebook", provider="Acme", category="",
                           trend_keywords=trends, performance=perf)
    fb_tags = [i["tag"] for i in fb]
    assert "#TagOne" in fb_tags and "#TagTwo" not in fb_tags, \
        "facebook's 2-tag cap keeps the measured winner, drops the measured loser"


def test_feedback_rollup_ignored_without_permission_even_with_data(monkeypatch):
    monkeypatch.delenv("MTK_ENABLE_DERIVED_ENGAGEMENT", raising=False)
    trends = ["tag one", "tag two", "tag three"]
    perf = {
        "#TagThree": {"posts": 50, "avg_impressions": 1.0},  # terrible record
    }
    base = generate_hashtags("youtube", provider="Acme", category="",
                             trend_keywords=trends, countries=["PK"])
    without_lift = generate_hashtags("youtube", provider="Acme", category="",
                                     trend_keywords=trends, countries=["PK"],
                                     performance=perf)
    assert base == without_lift, \
        "stored aggregates must not reshape generation unless permitted"


def test_generation_stays_deterministic():
    a = generate_hashtags("youtube", provider="Acme", category="ai_tools",
                          trend_keywords=["b", "a"], countries=["PK"])
    b = generate_hashtags("youtube", provider="Acme", category="ai_tools",
                          trend_keywords=["b", "a"], countries=["PK"])
    assert a == b


# --------------------------------------------------------------- gate reasons


def test_gate_blocks_count_placement_and_charset_violations():
    # YouTube needs 3–5 hashtags IN the description.
    yt = hashtag_gate_problems("youtube", {"caption": "no tags here", "tags": ["plain"] * 6})
    codes = {p["code"] for p in yt}
    assert "hashtag_count" in codes
    # Tag stuffing on Facebook.
    fb = hashtag_gate_problems("facebook", {"caption": "x #a #b #c #d"})
    assert any(p["code"] == "hashtag_count" for p in fb)
    # A malformed hashtag (symbols are not letters/digits/underscore/Urdu).
    bad = hashtag_gate_problems("instagram", {"caption": "#ok #bad!tag", "hashtags": ["#bad!tag"]})
    assert any(p["code"] == "hashtag_invalid" for p in bad)
    # Vanity tags are refused wherever they appear.
    vanity = hashtag_gate_problems("tiktok", {"caption": "#fyp #realtag"})
    assert any(p["code"] == "hashtag_forbidden" for p in vanity)
    # A correct package passes.
    good = hashtag_gate_problems("instagram", {"caption": "hook\n#Acme #Ai #Domain #Cloud"})
    assert good == []


def test_generated_youtube_package_passes_its_own_gate():
    meta = seo.build_metadata("youtube", OFFER, evidence_urls=["https://e/x"],
                              disclosure={}, trend_keywords=["ai domains"])
    problems = hashtag_gate_problems("youtube", meta)
    assert problems == [], problems
    assert meta["hashtags"] and all(t in meta["caption"] for t in meta["hashtags"][:3])
    assert all(not t.startswith("#") for t in meta["tags"])


def test_generated_comment_platforms_pass_their_own_gate():
    for platform in ("instagram", "tiktok", "facebook"):
        meta = seo.build_metadata(platform, OFFER, disclosure={})
        assert hashtag_gate_problems(platform, meta) == [], (platform, meta["hashtags"])


# ------------------------------------------------------------------ utilities


def test_hashtagify_and_parse_round_trip():
    assert hashtagify("example registrar") == "#ExampleRegistrar"
    assert hashtagify("") == ""
    parsed = parse_hashtags("hook #One two #three_x #اردو #One")
    assert parsed == ["#One", "#three_x", "#اردو"]
