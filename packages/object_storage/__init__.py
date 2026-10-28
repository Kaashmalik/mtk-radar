"""Object storage for MTK RADAR (v0.15) — capture videos, renders, captions.

The DB stores opaque REFS (scheme-prefixed strings), never host-local paths:
    s3://mtk-radar/renders/<offer>/<offer>-landscape.mp4
    local://renders/<offer>/<offer>-landscape.mp4     (single-host / NFS root)
    projects/<offer>/renders/....mp4                  (legacy, pre-storage rows)

Unset MTK_STORAGE_BACKEND → storage is disabled and workers keep writing
legacy relative paths (the documented single-host flow). Set the env and
workers publish refs instead; consumers materialize refs before use.

Import pattern (workers): the verification-worker sys.path shim —
    sys.path.insert(0, <repo>/packages)
    from object_storage import materialize, make_from_env, keys
"""

import os
import re
from pathlib import Path
from typing import Optional, Protocol

from ._local import LocalStorage, root_from_env
from ._s3 import S3Storage

SCHEMES = frozenset({"s3", "local"})


class Storage(Protocol):
    def put(self, local_path: Path, key: str) -> str: ...
    def get(self, ref: str, dest: Path) -> Path: ...
    def exists(self, ref: str) -> bool: ...
    def delete(self, ref: str) -> None: ...


# ---------------------------------------------------------------- keys

_SAFE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _safe_part(value: str, label: str) -> str:
    """Reject path separators and traversal in a key component."""
    text = str(value)
    if not _SAFE_PART.fullmatch(text) or ".." in text:
        raise ValueError(f"invalid {label} for storage key: {value!r}")
    return text


def _render_prefix(offer_id: str, revision: str | None,
                   attempt: str | None) -> tuple[str, str]:
    offer = _safe_part(offer_id, "offer id")
    parts = ["renders", offer]
    if revision:
        parts.append(_safe_part(revision, "revision"))
    prefix = "/".join(parts)
    stem = f"{_safe_part(attempt, 'attempt')}-" if attempt else ""
    return prefix, stem


def render_key(offer_id: str, preset: str, language: str | None = None, *,
               revision: str | None = None, attempt: str | None = None,
               ext: str = "mp4") -> str:
    """Immutable object key for one rendered variant.

    New callers pass a script revision and a unique render attempt so a rerun
    never overwrites a previously approved package. Omitting both keeps the
    legacy stable key for old code paths.
    """
    suffix = f"-{language}" if language and language != "en" else ""
    prefix, stem = _render_prefix(offer_id, revision, attempt)
    extension = _safe_part(ext.lstrip("."), "extension")
    return f"{prefix}/{stem}{_safe_part(offer_id, 'offer id')}-{_safe_part(preset, 'preset')}{suffix}.{extension}"


def captions_key(offer_id: str, preset: str, language: str | None = None, *,
                 revision: str | None = None,
                 attempt: str | None = None) -> str:
    suffix = f"-{language}" if language and language != "en" else ""
    prefix, stem = _render_prefix(offer_id, revision, attempt)
    return f"{prefix}/{stem}{_safe_part(offer_id, 'offer id')}-{_safe_part(preset, 'preset')}{suffix}.srt"


def cover_key(offer_id: str, preset: str, language: str | None = None,
              ext: str = "png", *, revision: str | None = None,
              attempt: str | None = None) -> str:
    suffix = f"-{language}" if language and language != "en" else ""
    prefix, stem = _render_prefix(offer_id, revision, attempt)
    extension = _safe_part(ext.lstrip("."), "extension")
    return (f"{prefix}/{stem}{_safe_part(offer_id, 'offer id')}-"
            f"{_safe_part(preset, 'preset')}{suffix}-cover.{extension}")


def capture_key(offer_id: str, session_id: str, filename: str) -> str:
    # Every key component obeys ONE rule: separators and odd characters are
    # rejected, so keys sign/URL-encode identically across S3 implementations.
    safe_name = _safe_part(Path(filename).name, "filename")
    return (f"captures/{_safe_part(offer_id, 'offer id')}/"
            f"{_safe_part(session_id, 'session id')}/{safe_name}")


def tts_key(sha256_hex: str, extension: str = "mp3") -> str:
    """Content-addressed narration audio (G25): identical speech is stored
    once and shared by every render host; the digest IS the identity."""
    digest = str(sha256_hex).lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("tts key needs a sha256 hex digest")
    return f"tts/{digest[:2]}/{digest}.{_safe_part(extension, 'extension')}"


def is_managed_ref(ref: str) -> bool:
    return "://" in str(ref) and str(ref).split("://", 1)[0] in SCHEMES


# ---------------------------------------------------------------- drivers


def make_s3_from_env() -> S3Storage | None:
    endpoint = os.environ.get("MTK_S3_ENDPOINT", "").strip()
    bucket = os.environ.get("MTK_S3_BUCKET", "").strip()
    access = os.environ.get("MTK_S3_ACCESS_KEY", "").strip()
    secret = os.environ.get("MTK_S3_SECRET_KEY", "").strip()
    if not (endpoint and bucket and access and secret):
        return None
    return S3Storage(
        endpoint=endpoint,
        bucket=bucket,
        access_key=access,
        secret_key=secret,
        region=os.environ.get("MTK_S3_REGION", "us-east-1"),
    )


def make_local_from_env() -> LocalStorage:
    return LocalStorage(root_from_env())


def make_from_env() -> Optional[Storage]:
    """Storage backend for UPLOADS. None when storage is disabled (legacy
    relative-path flow). MTK_STORAGE_BACKEND: 'local' | 's3' (case-insensitive)."""
    backend = os.environ.get("MTK_STORAGE_BACKEND", "").strip().lower()
    if backend == "local":
        return make_local_from_env()
    if backend == "s3":
        return make_s3_from_env()
    return None


def _driver_for_scheme(ref: str) -> Optional[Storage]:
    scheme = ref.split("://", 1)[0]
    if scheme == "local":
        return make_local_from_env()
    if scheme == "s3":
        return make_s3_from_env()
    return None


def materialize(ref: str, cache_dir: Path, storage: Optional[Storage] = None) -> Optional[Path]:
    """Turn a DB path/ref into a real, readable local file — the single entry
    point consumers (publishing, render, review tooling) rely on.

    - managed ref (s3://, local://) → downloaded/copied under cache_dir
    - plain path → returned as-is if it exists (legacy single-host rows)
    - returns None when the asset cannot be produced on THIS host
    """
    ref = str(ref)
    cache_dir = Path(cache_dir)
    if is_managed_ref(ref):
        driver = storage or _driver_for_scheme(ref)
        if driver is None:
            return None
        # stable cache path: filename under cache dir, keyed by prefix folders.
        # Traversal segments (`..`) are refused and the final dest is verified
        # to stay INSIDE cache_dir — refs reach us from DB rows/filenames, not
        # only from our own key builders.
        parts = [p for p in ref.split("://", 1)[1].split("/") if p]
        if any(p in ("..", ".") for p in parts):
            return None
        dest = cache_dir.joinpath(*parts[-3:]) if len(parts) >= 3 else cache_dir / parts[-1]
        try:
            dest.resolve().relative_to(cache_dir.resolve())
        except ValueError:
            return None
        try:
            return driver.get(ref, dest)
        except (FileNotFoundError, OSError, ValueError):
            return None
    path = Path(ref)
    return path if path.is_file() else None


__all__ = [
    "Storage",
    "LocalStorage",
    "S3Storage",
    "make_from_env",
    "make_local_from_env",
    "make_s3_from_env",
    "materialize",
    "is_managed_ref",
    "render_key",
    "captions_key",
    "cover_key",
    "capture_key",
    "root_from_env",
]
