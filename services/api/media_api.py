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

import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

import db
from api_hardening import CREDENTIAL_DISABLED, CREDENTIAL_REVIEWER, credential_class

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

# WP-G (§5.6.4): documented retention for non-pinned media artifacts; the
# media_gc endpoint's default cutoff (dry run first — a real run is audited).
MEDIA_RETENTION_DAYS = int(os.environ.get("MTK_MEDIA_RETENTION_DAYS", "90"))


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


# ------------------------------------------------------- media GC (WP-G §5.6.4)

#: Documented retention policy (docs): media artifacts older than this that
#: are NOT pinned may be reclaimed. `media_gc` never decides on its own —
#: a dry run lists candidates first, a real run is audited.
class MediaGcIn(BaseModel):
    dry_run: bool = True
    retention_days: int = Field(default=MEDIA_RETENTION_DAYS, ge=1, le=3650)


async def _gc_candidates(pool, cutoff_days: int) -> list[dict[str, Any]]:
    """Artifacts past retention that are NOT pinned.

    Pinned (exempt) = referenced by a schedule whose state is NOT cancelled
    or failed — every state that can still publish or is live pins its exact
    package. Renders keep their own columns; a capture's video does too.
    Legacy plain paths are returned as-is; managed refs (local://, s3://)
    carry their scheme.
    """
    rows = await pool.fetch(
        """
        WITH pinned_renders AS (
            SELECT DISTINCT s.render_id AS id
            FROM schedules s
            WHERE s.render_id IS NOT NULL
              AND s.state::text NOT IN ('cancelled', 'failed')
        ),
        pinned_captures AS (
            SELECT DISTINCT r.capture_id AS id
            FROM renders r
            WHERE r.capture_id IS NOT NULL
              AND r.id IN (SELECT id FROM pinned_renders)
        )
        SELECT 'render_video' AS artifact, r.id::text AS ref_id,
               r.video_path AS ref, r.created_at
        FROM renders r
        WHERE r.created_at < now() - make_interval(days => $1)
          AND r.id NOT IN (SELECT id FROM pinned_renders)
        UNION ALL
        SELECT 'render_captions', r.id::text, r.captions_path, r.created_at
        FROM renders r
        WHERE r.created_at < now() - make_interval(days => $1)
          AND r.id NOT IN (SELECT id FROM pinned_renders)
          AND r.captions_path IS NOT NULL
        UNION ALL
        SELECT 'capture_video', c.id::text, c.video_path, c.created_at
        FROM capture_sessions c
        WHERE c.created_at < now() - make_interval(days => $1)
          AND c.id NOT IN (SELECT id FROM pinned_captures)
          AND c.video_path IS NOT NULL
        ORDER BY created_at ASC
        """,
        cutoff_days,
    )
    return [dict(r) for r in rows]


def _delete_ref(ref: str) -> bool:
    """Delete ONE artifact ref (managed or host-local legacy path).

    Legacy paths are only deleted when they resolve to a file INSIDE this
    repository checkout — the endpoint must never become an arbitrary file
    deletion primitive. Returns True when something was deleted.
    """
    from object_storage import make_local_from_env, make_s3_from_env
    if ref.startswith("local://"):
        local = make_local_from_env()
        path = local.root / local.parse_ref(ref)
        existed = path.is_file()
        path.unlink(missing_ok=True)
        return existed
    if ref.startswith("s3://"):
        driver = make_s3_from_env()
        if driver is None:
            return False
        try:
            driver.delete(ref)
            return True
        except Exception:  # noqa: BLE001 — per-object failures are recorded, not fatal
            raise
    # Legacy host path — only within the repo checkout.
    candidate = Path(ref)
    options = [candidate] if candidate.is_absolute() else [
        Path.cwd() / candidate, REPO_ROOT / candidate]
    for option in options:
        resolved = option.resolve()
        if REPO_ROOT.resolve() not in resolved.parents:
            continue
        if resolved.is_file():
            resolved.unlink(missing_ok=True)
            return True
    return False


@router.post("/media/gc")
async def media_gc(body: MediaGcIn, request: Request) -> dict:
    """Retain non-pinned media for the documented 90-day policy, then offer
    reclamation (WP-G §5.6.4). Pinned artifacts — anything a live schedule
    (state not cancelled/failed) still references — are ALWAYS exempt.

    G05 (evidence-to-video plan): destructive reclamation is a HUMAN action —
    reviewer credential required (also enforced centrally in the auth
    middleware's route/role matrix; this check is the second lock).
    Dry run first (default): returns the exact candidate list; nothing is
    touched. `dry_run=false` deletes and writes an audit entry with every
    removed ref so the reclamation is reviewable afterwards.
    """
    if credential_class(request) not in (CREDENTIAL_REVIEWER, CREDENTIAL_DISABLED):
        raise HTTPException(status_code=403, detail=(
            "media GC is reviewer-only: a robot must not delete artifacts"))
    pool = db.get()
    candidates = await _gc_candidates(pool, body.retention_days)
    if body.dry_run:
        return {
            "mode": "dry_run", "retention_days": body.retention_days,
            "candidates": len(candidates),
            "items": [
                {"artifact": c["artifact"], "ref_id": c["ref_id"],
                 "ref": c["ref"], "created_at": str(c["created_at"])}
                for c in candidates
            ],
        }
    deleted, failed = 0, []
    removed_refs: list[str] = []
    for c in candidates:
        ref = str(c["ref"])
        try:
            if _delete_ref(ref):
                deleted += 1
                removed_refs.append(ref)
        except Exception as exc:  # noqa: BLE001 — one bad object never stops a GC run
            failed.append({"ref": ref, "error": str(exc)[:300]})
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, $3, NULL, $4::jsonb)",
        "system:media_gc", "media:gc", "media",
        json.dumps({
            "mode": "apply", "retention_days": body.retention_days,
            "deleted": deleted, "failed": failed, "removed_refs": removed_refs,
        }, default=str),
    )
    return {
        "mode": "apply", "retention_days": body.retention_days,
        "deleted": deleted, "failed": failed,
    }
