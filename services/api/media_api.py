"""Authenticated media playback (v0.31).

The review desk needs to WATCH captured footage and exported renders. Until
now the dashboard only printed a storage key, so the redaction-review gate was
attested without playback in the product.

These routes stay behind the normal bearer/session middleware: the dashboard
proxy attaches the signed reviewer session server-side, so a browser never
holds a storage credential. Byte ranges are forwarded so seeking works; S3
objects are streamed rather than buffered.

Media refs come from the database, never from the caller, so they cannot be
used to probe arbitrary paths or buckets.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

import db

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "packages"))

from object_storage import (  # noqa: E402
    LocalStorage,
    S3Storage,
    is_managed_ref,
    make_local_from_env,
    make_s3_from_env,
)

router = APIRouter(tags=["media"])

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_CHUNK = 256 * 1024
_S3: S3Storage | None = None


def _s3() -> S3Storage | None:
    global _S3
    if _S3 is None:
        _S3 = make_s3_from_env()
    return _S3


def parse_range(header: Optional[str], size: int) -> Optional[tuple[int, int]]:
    """Parse a single `bytes=` range into inclusive offsets.

    Returns None when the header is absent/unparseable (serve the whole file),
    and raises 416 when the range is well-formed but unsatisfiable.
    """
    if not header:
        return None
    match = _RANGE.fullmatch(header.strip())
    if not match:
        return None
    first, last = match.group(1), match.group(2)
    if first == "" and last == "":
        return None
    if first == "":
        suffix = int(last)
        if suffix <= 0:
            raise HTTPException(
                status_code=416,
                detail="invalid byte range",
                headers={"Content-Range": f"bytes */{size}"},
            )
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(first)
        end = int(last) if last else size - 1
    if size <= 0 or start >= size or end < start:
        raise HTTPException(
            status_code=416,
            detail="requested range is not satisfiable",
            headers={"Content-Range": f"bytes */{size}"},
        )
    return start, min(end, size - 1)


def _legacy_path(ref: str) -> Optional[Path]:
    candidate = Path(ref)
    options = [candidate] if candidate.is_absolute() else [
        candidate, Path.cwd() / candidate, REPO_ROOT / candidate,
    ]
    for option in options:
        if option.is_file():
            return option
    return None


def _local_path(ref: str) -> Optional[Path]:
    try:
        key = LocalStorage.parse_ref(ref)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = make_local_from_env().root / key
    return path if path.is_file() else None


def _serve_local(path: Path) -> FileResponse:
    # Starlette's FileResponse implements Range/If-Range and ETag handling, so
    # the browser can seek without this route re-implementing HTTP semantics.
    return FileResponse(
        path,
        media_type="video/mp4",
        headers={"Cache-Control": "private, no-store"},
    )


def _serve_s3(ref: str, range_header: Optional[str]) -> StreamingResponse:
    driver = _s3()
    if driver is None:
        raise HTTPException(
            status_code=503,
            detail="media is stored in object storage but MTK_S3_* is not configured",
        )
    size = driver.size(ref)
    if size is None:
        raise HTTPException(status_code=404, detail="media object not found")

    span = parse_range(range_header, size)
    start, end = span if span else (None, None)
    upstream = driver.open_stream(ref, start, end)
    if upstream.status_code == 416:
        upstream.close()
        raise HTTPException(
            status_code=416,
            detail="requested range is not satisfiable",
            headers={"Content-Range": upstream.headers.get(
                "content-range", f"bytes */{size}")},
        )
    if upstream.status_code == 404:
        upstream.close()
        raise HTTPException(status_code=404, detail="media object not found")
    if upstream.status_code >= 400:
        upstream.close()
        raise HTTPException(status_code=502, detail="storage backend refused the read")

    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
        "Content-Length": str(end - start + 1) if span and start is not None else str(size),
    }
    if span:
        headers["Content-Range"] = upstream.headers.get(
            "content-range", f"bytes {start}-{end}/{size}")
    if upstream.headers.get("etag"):
        headers["ETag"] = upstream.headers["etag"]

    def body():
        try:
            for chunk in upstream.iter_bytes(_CHUNK):
                yield chunk
        finally:
            upstream.close()

    return StreamingResponse(
        body(),
        status_code=206 if span else 200,
        media_type="video/mp4",
        headers=headers,
    )


def _serve_ref(ref: str, request: Request):
    if is_managed_ref(ref):
        if ref.startswith("local://"):
            path = _local_path(ref)
            if path is None:
                raise HTTPException(status_code=404, detail="media object not found")
            return _serve_local(path)
        return _serve_s3(ref, request.headers.get("range"))

    path = _legacy_path(ref)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="media is not available on this host — configure MTK_STORAGE_BACKEND",
        )
    return _serve_local(path)


@router.get("/renders/{render_id}/video")
async def render_video(render_id: uuid.UUID, request: Request):
    pool = db.get()
    row = await pool.fetchrow(
        "SELECT video_path FROM renders WHERE id = $1", render_id
    )
    if not row or not row["video_path"]:
        raise HTTPException(status_code=404, detail="render has no registered video")
    return _serve_ref(str(row["video_path"]), request)


@router.get("/captures/{capture_id}/video")
async def capture_video(capture_id: uuid.UUID, request: Request):
    pool = db.get()
    row = await pool.fetchrow(
        "SELECT video_path FROM capture_sessions WHERE id = $1", capture_id
    )
    if not row or not row["video_path"]:
        raise HTTPException(status_code=404, detail="capture has no recorded video")
    return _serve_ref(str(row["video_path"]), request)
