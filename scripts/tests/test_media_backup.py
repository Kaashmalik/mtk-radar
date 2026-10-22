"""Media backup tests — copy, manifest, verification, prune safety."""

import json
from pathlib import Path

from media_backup import (
    MANIFEST_NAME,
    prune_snapshots,
    run,
    sha256_file,
    verify_snapshot,
    write_manifest,
)


def make_source(root: Path) -> Path:
    source = root / "source"
    (source / "captures").mkdir(parents=True)
    (source / "captures" / "walkthrough.mp4").write_bytes(b"video-bytes")
    (source / "renders").mkdir()
    (source / "renders" / "cover.svg").write_text("<svg/>", encoding="utf-8")
    (source / ".env").write_text("TTS_API_KEY=do-not-back-up", encoding="utf-8")
    (source / "private.key").write_text("secret", encoding="utf-8")
    return source


def test_backup_copies_media_and_excludes_secrets(tmp_path: Path):
    source = make_source(tmp_path)
    result = run(source, tmp_path / "backup", keep=3)
    snapshot = Path(result["snapshot"])
    assert result["ok"] is True
    assert (snapshot / "captures" / "walkthrough.mp4").read_bytes() == b"video-bytes"
    assert not (snapshot / ".env").exists()
    assert not (snapshot / "private.key").exists()
    manifest = json.loads((snapshot / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["file_count"] == 2
    assert manifest["total_bytes"] == len(b"video-bytes") + len("<svg/>")


def test_verification_detects_tampering(tmp_path: Path):
    source = make_source(tmp_path)
    result = run(source, tmp_path / "backup", keep=3)
    snapshot = Path(result["snapshot"])
    assert verify_snapshot(snapshot)["ok"] is True

    (snapshot / "captures" / "walkthrough.mp4").write_bytes(b"video-bytez")
    verification = verify_snapshot(snapshot)
    assert verification["ok"] is False
    assert any("hash mismatch" in failure for failure in verification["failures"])


def test_missing_file_and_manifest_are_reported(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = verify_snapshot(empty)
    assert result["ok"] is False
    assert "manifest.json missing" in result["failures"][0]

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    write_manifest(snapshot, {"files": [{"path": "gone.mp4", "bytes": 1, "sha256": "x"}]})
    result = verify_snapshot(snapshot)
    assert result["ok"] is False
    assert any("missing" in failure for failure in result["failures"])


def test_prune_keeps_newest_and_never_deletes_unrelated_dirs(tmp_path: Path):
    root = tmp_path / "media"
    for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        snapshot = root / stamp
        snapshot.mkdir(parents=True)
        write_manifest(snapshot, {"files": []})
    unrelated = root / "notes"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("keep", encoding="utf-8")

    removed = prune_snapshots(root, keep=2)
    assert [path.name for path in removed] == ["20260101T000000Z"]
    assert (root / "20260103T000000Z").exists()
    assert (unrelated / "keep.txt").exists()


def test_hash_helper_reads_large_file_in_chunks(tmp_path: Path):
    path = tmp_path / "large.bin"
    path.write_bytes(b"x" * (3 * 1024 * 1024 + 17))
    assert len(sha256_file(path)) == 64


def test_dry_run_does_not_create_a_snapshot(tmp_path: Path):
    source = make_source(tmp_path)
    result = run(source, tmp_path / "backup", dry_run=True)
    assert result["dry_run"] is True
    assert not (tmp_path / "backup" / "media").exists()
