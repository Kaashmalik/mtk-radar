"""v0.27 cover generation: deterministic SVG, RTL, safe escaping."""

from pathlib import Path

from covers import build_cover_spec, generate_covers, render_svg

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
