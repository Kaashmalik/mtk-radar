"""SEO / packaging tests — platform limits, tracked CTA, bilingual metadata."""

from seo import (
    PLATFORM_LIMITS,
    build_hashtags,
    build_metadata,
    build_variants,
    with_utm,
)

OFFER = {
    "id": "offer-1",
    "title": "One-year .tech domain",
    "provider": "Example Registrar",
    "category": "domains_hosting",
    "eligibility": {"countries": ["PK"], "studentStatus": True},
    "renewal": {"regularPrice": "$12/year", "autoRenew": True},
}


def test_every_platform_respects_caption_limit():
    for platform, limits in PLATFORM_LIMITS.items():
        meta = build_metadata(platform, OFFER, evidence_urls=["https://example.com/terms"])
        assert len(meta["caption"]) <= limits["caption"]


def test_tiktok_and_instagram_have_no_title_field():
    for platform in ("tiktok", "instagram"):
        assert build_metadata(platform, OFFER)["title"] == ""


def test_website_link_gets_utm_and_keeps_existing_query():
    tracked = with_utm(
        "https://mtk.example/guide?ref=video",
        platform="youtube",
        offer_id="offer-1",
        language="ur",
    )
    assert "ref=video" in tracked
    assert "utm_source=youtube" in tracked
    assert "utm_content=offer-1-ur" in tracked


def test_pinned_comment_reuses_the_tracked_website():
    meta = build_metadata("youtube", OFFER, website_url="https://mtk.example/guide")
    assert "utm_source=youtube" in meta["pinned_comment"]
    assert meta["website_url"] in meta["pinned_comment"]


def test_urdu_metadata_contains_urdu_and_regional_hashtags():
    meta = build_metadata("instagram", OFFER, language="ur",
                          website_url="https://mtk.example/guide")
    assert meta["language"] == "ur"
    assert any("\u0600" <= char <= "\u06ff" for char in meta["caption"])
    assert "#اردو" in meta["hashtags"]


def test_hashtags_are_deduplicated_and_respect_count_order():
    tags = build_hashtags(OFFER, "instagram", language="en", limit=8)
    assert len(tags) == 8
    assert len({tag.lower() for tag in tags}) == 8


def test_ab_variants_differ_for_title_platforms():
    a, b = build_variants("youtube", OFFER)
    assert a["variant"] == "default"
    assert b["variant"] == "b"
    assert a["title"] != b["title"]
    assert a["platform"] == b["platform"] == "youtube"


def test_disclosure_and_evidence_are_packaged():
    meta = build_metadata(
        "facebook", OFFER,
        evidence_urls=["https://example.com/terms"],
        disclosure={"synthetic_narration": True},
    )
    assert "AI-generated" in meta["caption"]
    assert "https://example.com/terms" in meta["caption"]
