"""SEO / packaging tests — platform limits, tracked CTA, bilingual metadata."""

from seo import (
    PLATFORM_LIMITS,
    build_hashtags,
    build_metadata,
    build_variants,
    metadata_summary,
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


# --------------------------------------- 2026 packaging rules (YT playbook)

def test_youtube_title_fits_mobile_and_variants_differ():
    long_offer = {**OFFER, "title": "Six months of the developer plan completely free for verified students in eligible countries"}
    a, b = build_variants("youtube", long_offer, channel_name="MTK Codex")
    assert len(a["title"]) <= 50, a["title"]
    assert len(b["title"]) <= 50, b["title"]
    assert a["title"] != b["title"]
    # A short base title is preserved, not padded into cryptic fragments.
    short = build_metadata("youtube", {**OFFER, "title": "Free .tech domain"})
    assert "Free .tech domain" in short["title"]


def test_youtube_tags_are_few_plain_and_branded():
    meta = build_metadata("youtube", OFFER, channel_name="MTK Codex")
    tags = meta["tags"]
    assert 5 <= len(tags) <= 8, tags
    assert all(not t.startswith("#") for t in tags), "hashtags belong in the description, not tags"
    assert "free domain" in tags, "the broad category keyword leads"
    assert any("2026" in t for t in tags), "a dated sub-keyword targets current searches"
    assert tags[-1] == "mtk codex", "the channel name is the branded tag"
    assert len(" ".join(tags)) <= 500
    # Instagram keeps the legacy hashtag behaviour.
    ig = build_metadata("instagram", OFFER)
    assert ig["tags"] and all(t.startswith("#") for t in ig["tags"])


def test_thumbnail_text_is_three_words_max_and_not_the_title():
    from seo import build_thumbnail_text
    with_promo = {**OFFER, "title": "One-year .tech domain for students",
                  "promo_code": "SAVE2026"}
    text = build_thumbnail_text(with_promo)
    assert 0 < len(text.split()) <= 3
    assert text == "SAVE2026", "the specific verified fact wins"
    # A code that ALSO appears in the title is not fresh — fall through.
    self_referential = build_thumbnail_text(
        {**OFFER, "title": "SAVE2026 free domain", "promo_code": "SAVE2026"})
    assert "SAVE2026" not in self_referential
    assert len(self_referential.split()) <= 3
    # No specifics at all → the verified badge, never the title itself.
    plain = build_thumbnail_text({"title": "A very long descriptive runtime title"})
    assert len(plain.split()) <= 3
    assert plain.lower() not in plain.lower() or plain == "VERIFIED CLAIM"


def test_metadata_summary_carries_the_plain_tags():
    meta = build_metadata("youtube", OFFER, channel_name="MTK Codex")
    summary = metadata_summary(meta)
    assert summary["tags"] == meta["tags"]

def test_title_suffix_matches_what_the_script_format_may_claim():
    explainer = build_metadata("youtube", OFFER, format_hint="official_explainer")
    assert "official terms explained" in explainer["title"]
    assert "real claim walkthrough" not in explainer["title"], \
        "an explainer script makes no performed claim — the title must not either"

    claim = build_metadata("youtube", OFFER, format_hint="claim_walkthrough")
    assert "real claim walkthrough" in claim["title"]

    unknown = build_metadata("youtube", OFFER)
    assert "real claim" not in unknown["title"], \
        "without a format the suffix stays neutral, never a performed claim"


def test_variants_thread_the_format_hint():
    a, b = build_variants("youtube", OFFER, format_hint="official_explainer")
    assert "official terms explained" in a["title"]
    assert "real claim walkthrough" not in b["title"]
