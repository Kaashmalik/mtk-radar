"""Caption widths measured with the real font (V9)."""

from pathlib import Path

import pytest

import fontmetrics
from fontmetrics import ESTIMATE_FACTOR, measurer, resolve_font_file


def _any_system_font():
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                      "C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial.ttf",
                      "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if Path(candidate).is_file():
            return candidate
    return None


@pytest.fixture(autouse=True)
def _fresh_cache():
    resolve_font_file.cache_clear()
    yield
    resolve_font_file.cache_clear()


def test_unknown_font_falls_back_to_a_labelled_estimate(monkeypatch):
    monkeypatch.delenv("MTK_CAPTION_FONT_FILE", raising=False)
    m = measurer("No Such Font Family 12345", 50)
    assert m.method == "estimate"
    assert m.width("abcd") == pytest.approx(4 * 50 * ESTIMATE_FACTOR)
    assert m.width("") == 0.0


def test_explicit_font_file_wins(monkeypatch):
    font = _any_system_font()
    if not font:
        pytest.skip("no system TrueType font on this host")
    monkeypatch.setenv("MTK_CAPTION_FONT_FILE", font)
    assert resolve_font_file("Whatever Family") == font


def test_real_font_distinguishes_wide_from_narrow_glyphs(monkeypatch):
    font = _any_system_font()
    if not font:
        pytest.skip("no system TrueType font on this host")
    pytest.importorskip("PIL")
    monkeypatch.setenv("MTK_CAPTION_FONT_FILE", font)
    m = measurer("Caption", 52)
    assert m.method.startswith("font:")
    wide, narrow = m.width("WWWWWWWW"), m.width("iiiiiiii")
    assert wide > 2 * narrow, "a per-character estimate cannot see this difference"


def test_libass_scaling_rule_is_applied(monkeypatch):
    font = _any_system_font()
    if not font:
        pytest.skip("no system TrueType font on this host")
    PIL_font = pytest.importorskip("PIL.ImageFont")
    monkeypatch.setenv("MTK_CAPTION_FONT_FILE", font)
    raw = PIL_font.truetype(font, 52)
    ascent, descent = raw.getmetrics()
    expected = raw.getlength("Readable caption") * 52 / (ascent + descent)
    assert measurer("Caption", 52).width("Readable caption") == pytest.approx(expected)


def test_qc_reports_which_width_method_it_used(tmp_path):
    import qc
    from captions import to_ass

    path = tmp_path / "c.ass"
    path.write_text(to_ass([{"text": "Hello world", "start": 0, "end": 2}]), encoding="utf-8")
    check = qc.check_captions(path, width=1920, height=1080, config=qc.QCConfig())
    assert check["details"]["width_method"] in ("estimate",) or \
        check["details"]["width_method"].startswith("font:")


def test_measurement_failure_never_breaks_qc(monkeypatch, tmp_path):
    bogus = tmp_path / "broken.ttf"
    bogus.write_bytes(b"not a font")
    monkeypatch.setenv("MTK_CAPTION_FONT_FILE", str(bogus))
    fontmetrics._load.cache_clear()
    m = measurer("Caption", 40)
    assert m.width("abc") == pytest.approx(3 * 40 * ESTIMATE_FACTOR)
