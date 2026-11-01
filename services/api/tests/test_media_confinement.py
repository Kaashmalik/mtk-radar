"""Legacy media path confinement (review P1-2): refusing absolute/extreme
refs before files, allowing only the managed roots.

The render/capture video routes serve refs from database rows, not the
request — but a hostile or poisoned WRITER must not turn the legacy
plain-path fallback into a read-any-file primitive. The page-capture image
route already refuses host paths outright; the same discipline applies to
the render/capture video refs resolved by `_legacy_path`.
"""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from media_api import _legacy_path, _serve_ref, legacy_allowed_roots

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_absolute_host_paths_are_refused(tmp_path):
    """A real, readable absolute file must still be refused — pre-fix this
    exact case served any readable file on the host."""
    secret = tmp_path / "legacy-absolute.mp4"
    secret.write_bytes(b"private")
    assert _legacy_path(str(secret)) is None
    assert _legacy_path("C:/Windows/win.ini") is None
    assert _legacy_path("/etc/passwd") is None


def test_traversal_refs_are_refused():
    hostile = (
        "../../etc/passwd",
        "services/api/../../.env",
        "storage/renders/../../../../Windows/win.ini",
        "projects/x/../../secrets.mp4",
    )
    for ref in hostile:
        assert _legacy_path(ref) is None, ref


def test_in_repo_legacy_relative_path_still_resolves():
    """The documented single-host legacy flow keeps working: pre-storage DB
    rows store paths relative to the repo root."""
    found = _legacy_path("services/api/media_api.py")
    assert found is not None
    assert found.is_file()
    assert found.name == "media_api.py"


def test_storage_local_root_is_a_managed_root(tmp_path, monkeypatch):
    """A deployment with a custom local storage root keeps resolving legacy
    refs inside it — confinement is to the MANAGED roots, not just the repo."""
    monkeypatch.setenv("MTK_STORAGE_LOCAL_ROOT", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"legacy ref")
    assert _legacy_path("clip.mp4") == clip
    monkeypatch.setenv("MTK_STORAGE_LOCAL_ROOT", str(tmp_path / "none"))
    assert Path(tmp_path / "clip.mp4").is_file()
    assert _legacy_path("clip.mp4") is None, (
        "the same relative ref must stop resolving once it is outside "
        "ALL managed roots")


def test_materialization_cache_is_a_managed_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MTK_STORAGE_CACHE", str(tmp_path))
    clip = tmp_path / "materialized.mp4"
    clip.write_bytes(b"cached")
    assert _legacy_path("materialized.mp4") == clip


def test_serve_ref_fails_closed_on_an_escaping_ref():
    """The GET /renders/{id}/video + /captures/{id}/video serving path turns
    a refused legacy ref into the same 404 as a missing file — never a 500
    and never the file."""
    with pytest.raises(HTTPException) as escaped:
        _serve_ref("/etc/passwd", _request_stub())
    assert escaped.value.status_code == 404
    with pytest.raises(HTTPException) as traversed:
        _serve_ref("storage/../../../../etc/passwd", _request_stub())
    assert traversed.value.status_code == 404


def test_serve_ref_serves_an_in_repo_legacy_relative_path():
    """The legitimate legacy flow still serves (private, no-store)."""
    import media_api

    response = _serve_ref("services/api/media_api.py", _request_stub())
    assert isinstance(response, media_api.FileResponse)


def test_legacy_allowed_roots_cover_exactly_the_managed_directories():
    names = {root.name for root in legacy_allowed_roots()}
    assert "mtk-radar" in names or REPO_ROOT.name in names  # repo checkout
    assert "storage" in names                                # local storage root
    assert ".storage-cache" in names                         # materialize cache


def _request_stub():
    """`_serve_ref` only reads the Range header; a bare Request suffices."""
    from starlette.requests import Request

    return Request({"type": "http", "method": "GET", "path": "/",
                   "headers": [], "query_string": b""})
