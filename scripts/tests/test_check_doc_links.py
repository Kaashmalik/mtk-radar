"""Guard the documentation link checker (DOC-16)."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import check_doc_links as links  # noqa: E402


def test_external_and_anchor_links_are_ignored(tmp_path: Path):
    page = tmp_path / "page.md"
    page.write_text(
        "[x](https://example.com) [y](#section) [z](mailto:a@b.test)",
        encoding="utf-8",
    )
    assert list(links.iter_links(page)) == []


def test_resolves_relative_and_percent_encoded_paths(tmp_path: Path):
    page = tmp_path / "page.md"
    target = tmp_path / "my doc.md"
    target.write_text("x", encoding="utf-8")
    page.write_text("[a](my%20doc.md) [b](missing.md)", encoding="utf-8")

    assert links.resolve(page, "my%20doc.md") == target
    assert not links.resolve(page, "missing.md").exists()


def test_repo_documentation_links_resolve():
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_doc_links.py")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
