"""v0.27 cover generation: deterministic SVG, RTL, safe escaping."""

from pathlib import Path

from covers import (build_cover_spec, build_thumbnail_text, cover_for_preset,
                    generate_covers, render_svg)

OFFER = {
    "title": "One-year .tech domain for students",
    "provider": "Example Registrar",
}


def test_spec_is_deterministic_and_preset_aware():
    a = build_cover_spec(OFFER, language="en", variant="a", preset="landscape")
    b = build_cover_spec(OFFER, language="en", variant="a", preset="landscape")
    vertical = build_cover_spec(OFFER, language="en", variant="a", preset="vertical")
    assert a == b
    assert (a["width"], a["height"]) == (1280, 720)
    assert (vertical["width"], vertical["height"]) == (1080, 1920)
    assert a["title_lines"]


def test_urdu_cover_is_rtl_and_uses_urdu_font():
    spec = build_cover_spec(OFFER, language="ur", variant="a")
    svg = render_svg(spec)
    assert 'direction="rtl"' not in svg or spec["rtl"] is True
    assert "Noto Nastaliq Urdu" in svg
    assert "تصدیق شدہ کلیم" in svg
    assert 'text-anchor="end"' in svg


def test_title_is_xml_escaped_not_injected():
    spec = build_cover_spec({**OFFER, "title": "Free <script>alert(1)</script>"})
    svg = render_svg(spec)
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_ab_variants_change_palette():
    a = build_cover_spec(OFFER, variant="a")
    b = build_cover_spec(OFFER, variant="b")
    assert a["palette"] != b["palette"]


def test_generate_writes_language_specific_assets(tmp_path: Path):
    bundle = generate_covers(tmp_path, OFFER, language="ur",
                             website_url="https://mtk.example/guide")
    assert len(bundle["covers"]) == 2
    for cover in bundle["covers"]:
        path = tmp_path / cover["svg"]
        assert path.is_file()
        assert path.read_text(encoding="utf-8").startswith("<svg")
    assert "ur-a-landscape.svg" in bundle["primary"]["svg"]


def test_cover_selection_matches_the_delivery_frame(tmp_path: Path):
    bundle = generate_covers(tmp_path, OFFER)
    vertical = cover_for_preset(bundle, "vertical")
    assert "vertical" in vertical["svg"], "a 9:16 render needs the 9:16 cover"
    assert cover_for_preset(bundle, "missing") == bundle["primary"]


# ------------------------------------ 2026 packaging rules (thumbnail text)

def test_thumbnail_text_is_three_words_max_and_not_the_title():
    promo_offer = {**OFFER, "promo_code": "SAVE2026"}
    spec = build_cover_spec(promo_offer, language="en", preset="landscape")
    # The specific verified fact wins and never repeats the title.
    assert spec["thumbnail_text"] == "SAVE2026"
    assert len(spec["thumbnail_text"].split()) <= 3
    assert spec["thumbnail_lines"] == ["SAVE2026"]
    # The big rendered text is the thumbnail text, not the full title.
    svg = render_svg(spec)
    assert ">SAVE2026<" in svg
    # The rendered <text> elements carry the thumbnail wording, never the
    # full title (the title survives only in the accessibility label).
    for chunk in render_svg(build_cover_spec({**OFFER, "promo_code": "SAVE2026"})).split("<text")[1:]:
        assert "tech domain" not in chunk.split("</text>")[0]
    # Without a promo the deterministic badge is used — still <=3 words.
    plain = build_cover_spec(OFFER)
    assert 0 < len(plain["thumbnail_text"].split()) <= 3


def test_both_implementations_agree_with_the_api_side():
    """workers/render/covers.build_thumbnail_text must stay in sync with
    services/api/seo.build_thumbnail_text — the release gate validates the
    studio-published text while this module draws the pixels."""
    import sys as _sys
    from pathlib import Path as _Path

    api_root = _Path(__file__).resolve().parents[3] / "services" / "api"
    _sys.path.insert(0, str(api_root))
    try:
        from seo import build_thumbnail_text as api_side
    finally:
        _sys.path.remove(str(api_root))

    offers = [
        OFFER,
        {**OFFER, "promo_code": "SAVE2026"},
        {**OFFER, "value": {"amount": 12, "currency": "credits"}},
        {"title": "Totally different runtime title", "provider": "X"},
    ]
    for offer in offers:
        assert build_thumbnail_text(offer) == api_side(offer), offer.get("title")
