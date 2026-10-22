"""Driver + facade behavior: local round-trip, S3 over a mocked transport,
key scheme, and worker-facing materialize() semantics."""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # packages/

import object_storage
from object_storage._local import LocalStorage
from object_storage import (
    S3Storage,
    captions_key,
    capture_key,
    cover_key,
    is_managed_ref,
    make_from_env,
    materialize,
    render_key,
)


# ---------------------------------------------------------------- keys


def test_key_scheme_is_deterministic_and_offer_scoped():
    assert render_key("o1", "landscape") == "renders/o1/o1-landscape.mp4"
    assert captions_key("o1", "vertical") == "renders/o1/o1-vertical.srt"
    assert capture_key("o1", "s1", "../../evil/path/vid.webm") == "captures/o1/s1/vid.webm"
    assert is_managed_ref("s3://b/k") and is_managed_ref("local://k")
    assert not is_managed_ref("projects/o1/renders/x.mp4")


def test_revision_attempt_keys_never_overwrite_an_approved_package():
    first = render_key("o1", "landscape", revision="v2-abc123", attempt="run1")
    second = render_key("o1", "landscape", revision="v2-abc123", attempt="run2")
    assert first == "renders/o1/v2-abc123/run1-o1-landscape.mp4"
    assert second != first
    assert captions_key("o1", "vertical", "ur", revision="v2-abc123",
                        attempt="run1") == (
        "renders/o1/v2-abc123/run1-o1-vertical-ur.srt")
    assert cover_key("o1", "landscape", revision="v2-abc123", attempt="run1",
                     ext="jpg") == (
        "renders/o1/v2-abc123/run1-o1-landscape-cover.jpg")


def test_key_parts_cannot_escape_the_prefix():
    for bad in ("../etc", "a/b", ".."):
        with pytest.raises(ValueError):
            render_key("o1", "landscape", revision=bad)
        with pytest.raises(ValueError):
            render_key("o1", "landscape", attempt=bad)


# ---------------------------------------------------------------- local driver


def test_local_roundtrip_and_atomicity(tmp_path: Path):
    root = tmp_path / "storage"
    drv = LocalStorage(root)
    src = tmp_path / "in.mp4"
    src.write_bytes(b"VIDEO")

    ref = drv.put(src, "renders/o1/o1-landscape.mp4")
    assert ref == "local://renders/o1/o1-landscape.mp4"
    assert drv.exists(ref)
    assert not list(root.rglob("*.partial")), "temp files must never survive a put"

    dest = tmp_path / "cache" / "landscape.mp4"
    out = drv.get(ref, dest)
    assert out.read_bytes() == b"VIDEO"

    drv.delete(ref)
    assert not drv.exists(ref)


def test_local_ref_rejects_traversal(tmp_path: Path):
    drv = LocalStorage(tmp_path / "s")
    with pytest.raises(ValueError):
        drv.parse_ref("local://../escape")


# ---------------------------------------------------------------- s3 driver


def _s3_with(handler) -> tuple[S3Storage, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def transport_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    st = S3Storage(
        endpoint="http://minio.local:9000",
        bucket="mtk-bucket",
        access_key="AKID",
        secret_key="SECRET",
        region="us-east-1",
        http=httpx.Client(transport=httpx.MockTransport(transport_handler)),
    )
    return st, seen


def test_s3_put_signs_and_returns_ref(tmp_path: Path):
    def ok(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    st, seen = _s3_with(ok)
    f = tmp_path / "r.mp4"
    f.write_bytes(b"VIDEO")
    ref = st.put(f, "renders/o1/o1-landscape.mp4")

    assert ref == "s3://mtk-bucket/renders/o1/o1-landscape.mp4"
    req = seen[0]
    assert req.method == "PUT"
    assert req.url.host == "minio.local" and req.url.port == 9000
    assert req.url.path == "/mtk-bucket/renders/o1/o1-landscape.mp4"
    from object_storage._sigv4 import sha256_hex as _sha
    assert req.headers["x-amz-content-sha256"] == _sha(b"VIDEO")
    auth = req.headers["authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKID/")
    assert "/us-east-1/s3/aws4_request, SignedHeaders=" in auth


def test_s3_get_downloads_bytes_and_reports_missing(tmp_path: Path):
    state = {"served": False}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "HEAD":
            return httpx.Response(200) if state["served"] else httpx.Response(404)
        if req.method == "GET":
            if state["served"]:
                return httpx.Response(200, content=b"VIDEO")
            return httpx.Response(404)
        return httpx.Response(405)

    st, seen = _s3_with(handler)
    assert st.exists("s3://mtk-bucket/gone.mp4") is False
    with pytest.raises(FileNotFoundError):
        st.get("s3://mtk-bucket/gone.mp4", tmp_path / "x.mp4")

    state["served"] = True
    assert st.exists("s3://mtk-bucket/here.mp4") is True
    out = st.get("s3://mtk-bucket/here.mp4", tmp_path / "cache" / "here.mp4")
    assert out.read_bytes() == b"VIDEO"
    # regression: str destinations must coerce (workers pass env strings)
    out2 = st.get("s3://mtk-bucket/here.mp4", str(tmp_path / "cache" / "str-dest.mp4"))
    assert out2.read_bytes() == b"VIDEO" and isinstance(out2, Path)


# ---------------------------------------------------------------- facade


def test_make_from_env_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MTK_STORAGE_BACKEND", raising=False)
    assert make_from_env() is None  # legacy relative-path flow preserved


def test_make_from_env_local_and_s3(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MTK_STORAGE_BACKEND", "local")
    monkeypatch.setenv("MTK_STORAGE_LOCAL_ROOT", str(tmp_path))
    assert type(make_from_env()).__name__ == "LocalStorage"

    monkeypatch.setenv("MTK_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("MTK_S3_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MTK_S3_BUCKET", "b")
    monkeypatch.setenv("MTK_S3_ACCESS_KEY", "k")
    monkeypatch.setenv("MTK_S3_SECRET_KEY", "s")
    assert type(make_from_env()).__name__ == "S3Storage"


def test_materialize_semantics(tmp_path: Path, monkeypatch):
    # plain path that exists → as-is (legacy rows)
    local_file = tmp_path / "projects" / "o1" / "r.mp4"
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"V")
    assert materialize(str(local_file), tmp_path / "cache") == local_file
    # plain path missing → None (the "not on this host" case)
    assert materialize(str(tmp_path / "nope.mp4"), tmp_path / "cache") is None

    # managed ref → downloaded through the driver into a stable cache path
    monkeypatch.setenv("MTK_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("MTK_S3_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("MTK_S3_BUCKET", "b")
    monkeypatch.setenv("MTK_S3_ACCESS_KEY", "k")
    monkeypatch.setenv("MTK_S3_SECRET_KEY", "s")

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"REMOTE")

    real_init = object_storage.S3Storage.__init__

    def fake_init(self, **kw):
        self.endpoint = kw["endpoint"]
        self.bucket = kw["bucket"]
        self.access_key = kw["access_key"]
        self.secret_key = kw["secret_key"]
        self.region = kw.get("region", "us-east-1")
        self._http = httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(object_storage.S3Storage, "__init__", fake_init)
    out = materialize("s3://b/renders/o1/o1-landscape.mp4", tmp_path / "cache")
    assert out is not None and out.read_bytes() == b"REMOTE"

    # managed ref with no driver configured → None, never a crash
    monkeypatch.delenv("MTK_S3_ENDPOINT", raising=False)
    assert materialize("s3://b/k.mp4", tmp_path / "cache") is None


def test_s3_list_returns_refs_under_a_prefix():
    """The off-host backup copy prunes old dumps through this listing."""
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "GET"
        assert req.url.path == "/mtk-bucket"
        assert "list-type=2" in str(req.url)
        assert "prefix=backups" in str(req.url)
        assert req.headers["authorization"].startswith("AWS4-HMAC-SHA256")
        # S3 ListObjectsV2 answers XML, not JSON
        return httpx.Response(200, text=(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            "<Contents><Key>backups/mtk_radar_20260101T000000Z.dump</Key></Contents>"
            "<Contents><Key>backups/mtk_radar_20260102T000000Z.dump</Key></Contents>"
            "</ListBucketResult>"
        ))

    st, _ = _s3_with(handler)
    refs = st.list("backups")
    assert refs == [
        "s3://mtk-bucket/backups/mtk_radar_20260101T000000Z.dump",
        "s3://mtk-bucket/backups/mtk_radar_20260102T000000Z.dump",
    ]


def test_s3_list_handles_an_empty_bucket():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"/>'
        ))

    st, _ = _s3_with(handler)
    assert st.list("backups") == []


def test_s3_list_also_accepts_json_stores():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Contents": [{"Key": "backups/x.dump"}]})

    st, _ = _s3_with(handler)
    assert st.list("backups") == ["s3://mtk-bucket/backups/x.dump"]
