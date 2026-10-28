"""Platform capability snapshots (G23 UX) — allowlist sanitizer, no DB."""

from platforms_api import sanitize_capabilities


def test_only_known_tiktok_fields_are_kept_and_bounded():
    raw = {
        "creator_username": "mtk", "creator_nickname": "MTK Radar",
        "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"] + ["X"] * 20,
        "comment_disabled": 1, "duet_disabled": False, "stitch_disabled": "",
        "max_video_post_duration_sec": "600",
        "access_token": "SHOULD-NOT-BE-STORED", "random": {"nested": True},
    }
    clean = sanitize_capabilities("tiktok", raw)
    assert "access_token" not in clean and "random" not in clean
    assert len(clean["privacy_level_options"]) == 10
    assert clean["comment_disabled"] is True and clean["stitch_disabled"] is False
    assert clean["max_video_post_duration_sec"] == 600


def test_other_platforms_store_nothing_yet():
    assert sanitize_capabilities("youtube", {"creator_username": "x"}) == {}
