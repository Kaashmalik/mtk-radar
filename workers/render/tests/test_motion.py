"""Branded motion filter tests."""

import pytest

from motion import build_motion_filter, describe, motion_metadata
from presets import get_preset


def test_none_is_the_legacy_export():
    assert build_motion_filter(get_preset("landscape"), title="x", template="none") == ""


def test_studio_motion_has_push_crop_and_lower_third():
    fragment = build_motion_filter(
        get_preset("landscape"),
        title="Student domain offer",
        provider="Example",
        language="en",
        duration_s=30,
        template="studio",
    )
    assert "scale=" in fragment and "crop=1920:1080" in fragment
    assert "eq=" in fragment
    assert "fade=t=in" in fragment and "fade=t=out" in fragment
    assert "drawtext=" in fragment
    assert "VERIFIED CLAIM" in fragment
    assert "sin(t" in fragment


def test_minimal_has_no_brand_overlay():
    fragment = build_motion_filter(get_preset("vertical"), title="x", template="minimal")
    assert "drawtext" not in fragment
    assert "crop=1080:1920" in fragment


def test_urdu_label_and_font_hint():
    fragment = build_motion_filter(get_preset("vertical"), title="x", language="ur")
    assert "تصدیق شدہ کلیم" in fragment


def test_drawtext_escaping_blocks_filter_injection():
    title_fragment = build_motion_filter(
        get_preset("landscape"), title="evil':x=0,drawtext=bad"
    )
    assert "evil\\'" in title_fragment
    provider_fragment = build_motion_filter(
        get_preset("landscape"), title="x", provider="a:b,c"
    )
    assert "a\\:b\\,c" in provider_fragment


def test_unknown_template_fails_loudly():
    with pytest.raises(ValueError):
        build_motion_filter(get_preset("landscape"), title="x", template="cinema")


def test_motion_metadata_is_manifest_ready():
    meta = motion_metadata("studio", "ur", preset="vertical")
    assert meta["motion_template"] == "studio"
    assert meta["language"] == "ur"
    assert "lower-third" in describe("studio")
