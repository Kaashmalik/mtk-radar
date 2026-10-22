"""Capture-lab QA — advisory checks before human redaction review."""

from qa import run_checks


MEDIA = {"duration_s": 95.0, "width": 1920, "height": 1080, "has_audio": True}
STEPS = [
    {"n": 0, "title": "open offer page", "kind": "manual_check"},
    {"n": 1, "title": "official terms", "kind": "verification", "url": "https://example.com/terms"},
    {"n": 2, "title": "claim result", "kind": "result"},
]


def test_good_capture_is_review_ready():
    result = run_checks("capture.mp4", STEPS, expected_steps=3, probe=lambda _: MEDIA)
    assert result["ok"] is True
    assert result["ready_for_review"] is True
    assert not result["warnings"] and not result["blocking"]


def test_missing_video_blocks_review():
    result = run_checks(None, STEPS, expected_steps=3, probe=lambda _: MEDIA)
    assert result["ok"] is False
    assert any("video_present" in item for item in result["blocking"])


def test_missing_step_log_blocks_review():
    result = run_checks("capture.mp4", [], expected_steps=3, probe=lambda _: MEDIA)
    assert result["ok"] is False
    assert any("step_log" in item for item in result["blocking"])


def test_missing_audio_is_a_fixable_warning():
    result = run_checks("capture.mp4", STEPS, probe=lambda _: {**MEDIA, "has_audio": False})
    assert result["ok"] is True
    assert result["ready_for_review"] is False
    assert any("no audio" in item for item in result["warnings"])


def test_short_or_low_resolution_capture_warns():
    result = run_checks(
        "capture.mp4", STEPS,
        probe=lambda _: {"duration_s": 3, "width": 320, "height": 240, "has_audio": True},
    )
    assert result["ok"] is True
    assert len(result["warnings"]) >= 2


def test_unreadable_media_is_blocking():
    result = run_checks("capture.mp4", STEPS, probe=lambda _: None)
    assert result["ok"] is False
    assert any("media_readable" in item for item in result["blocking"])


def test_missing_proof_step_is_visible_but_not_blocking():
    steps = [{"n": 0, "title": "open page", "kind": "manual_check"}]
    result = run_checks("capture.mp4", steps, probe=lambda _: MEDIA)
    assert result["ok"] is True
    assert any("proof_step" in item for item in result["warnings"])
