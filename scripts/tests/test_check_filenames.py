"""Guard the filename-portability lint (evidence-to-video plan G28/EP-00).

Two failure modes to keep loud:

1. a contributor adds a `:` (or other Windows-invalid) filename — CI on
   ubuntu never notices, Windows contributors/CI archives do;
2. the lint itself regresses (e.g. stops detecting invalid segments).

No bad file is ever created in the repo: segmentation logic is unit-tested
directly and the end-to-end run is exercised against a temp git tree.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import check_filenames as cf  # noqa: E402


def test_reasonable_segments_pass():
    assert cf.check_segment("worker_v2.py") is None
    assert cf.check_segment("release notes 2026.md") is None
    assert cf.check_segment(".github") is None
    assert cf.check_segment("Dockerfile") is None


def test_windows_invalid_characters_are_caught():
    for bad in ("a:b.md", "a<b", 'a"b', "a|b", "a?b", "a*b"):
        assert cf.check_segment(bad) is not None, bad


def test_control_characters_trailing_dots_and_reserved_names():
    assert cf.check_segment("a\x01b") is not None
    assert cf.check_segment("name.") is not None
    assert cf.check_segment("name ") is not None
    for name in ("CON", "con.txt", "NUL", "com1", "LPT9"):
        assert cf.check_segment(name) is not None, name


def test_repo_itself_is_clean():
    """The lint run over the real repo must pass — this is the guard that
    keeps new ':' documents (G28) out of the tree."""
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_filenames.py")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_detects_bad_name_in_a_temp_tree(tmp_path: Path):
    bad = tmp_path / "TikTok Guide: 2026.md"
    bad.write_text("x")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", bad.name], cwd=tmp_path, check=True)

    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_filenames.py"), "."],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "TikTok Guide: 2026.md" in result.stderr
