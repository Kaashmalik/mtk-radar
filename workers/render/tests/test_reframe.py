"""Activity-following vertical reframing (V5) — pure functions, no FFmpeg."""

import subprocess

import pytest

import reframe
from reframe import (Keyframe, camera_path, crop_x_expr, focus_samples,
                     split_frames, vertical_focus_chain)

W, H = reframe.SAMPLE_W, reframe.SAMPLE_H


def _frame(active_cols=None, value=200):
    """A grey frame; `active_cols` = (start, end) columns painted bright."""
    data = bytearray([40] * (W * H))
    if active_cols:
        start, end = active_cols
        for y in range(H // 3, 2 * H // 3):
            for x in range(start, end):
                data[y * W + x] = value
    return bytes(data)


def test_focus_follows_where_the_screen_changes():
    frames = [_frame(), _frame((150, 170)), _frame(), _frame((20, 40))]
    samples = focus_samples(frames)
    assert samples[0] is None
    assert samples[1] == pytest.approx(160 / W, abs=0.02), "typing on the right"
    assert samples[3] == pytest.approx(30 / W, abs=0.02), "then on the left"


def test_static_or_whole_page_changes_have_no_single_focus():
    still = focus_samples([_frame(), _frame()])
    page_switch = focus_samples([_frame(), bytes([220] * (W * H))])  # new page
    assert still[1] is None and page_switch[1] is None


def test_camera_is_smoothed_clamped_and_refuses_weak_signals():
    samples = [0.9] * 20
    keys = camera_path(samples, crop_frac=0.5)
    assert keys and all(0.25 <= k.center <= 0.75 for k in keys), "window stays inside"
    assert keys[-1].center == pytest.approx(0.75)
    assert camera_path([None] * 18 + [0.5, 0.5], crop_frac=0.5) is None
    # Tiny jitters inside the dead zone do not move the camera.
    calm = camera_path([0.5, 0.52, 0.49, 0.51] * 10, crop_frac=0.5)
    assert {k.center for k in calm} == {0.5}


def test_crop_expression_interpolates_and_stays_in_frame():
    keys = [Keyframe(0, 0.25), Keyframe(2, 0.75)]
    expr = crop_x_expr(keys, src_w=1920, crop_w=960)
    assert expr == "if(lt(t,2),0+(960)*(t-0)/2,960)"
    assert crop_x_expr([Keyframe(0, 0.0)], 1920, 960) == "0", "clamped at the left edge"
    assert crop_x_expr([Keyframe(0, 1.0)], 1920, 960) == "960", "clamped at the right edge"


def test_chain_produces_the_same_vbase_contract_as_the_preset():
    chain = vertical_focus_chain([Keyframe(0, 0.5)], crop_frac=0.5)
    assert chain.startswith("[0:v]split=2[bg][fg];") and chain.endswith("[vbase]")
    assert "crop=w=960:h=1080:x='480':y=0" in chain
    assert "scale=1080:-2" in chain, "foreground fills the phone width"


def test_opt_in_and_width_bounds(monkeypatch):
    monkeypatch.delenv("MTK_VERTICAL_REFRAME", raising=False)
    assert reframe.enabled() is False
    monkeypatch.setenv("MTK_VERTICAL_REFRAME", "auto")
    assert reframe.enabled() is True
    monkeypatch.setenv("MTK_VERTICAL_REFRAME_WIDTH", "0.1")
    assert reframe.crop_fraction() == 0.35
    monkeypatch.setenv("MTK_VERTICAL_REFRAME_WIDTH", "x")
    assert reframe.crop_fraction() == 0.5


def test_analyse_end_to_end_with_a_fake_sampler():
    raw = b"".join([_frame(), _frame((150, 170))] * 10)

    def fake_run(cmd, capture_output, timeout):
        assert "format=gray" in " ".join(cmd)
        return subprocess.CompletedProcess(cmd, 0, raw, b"")

    keys = reframe.analyse("cap.mkv", 0.5, run=fake_run)
    assert keys and keys[-1].center > 0.6
    assert len(split_frames(raw)) == 20
    failing = lambda cmd, capture_output, timeout: subprocess.CompletedProcess(cmd, 1, b"", b"x")  # noqa: E731
    assert reframe.analyse("cap.mkv", 0.5, run=failing) is None
