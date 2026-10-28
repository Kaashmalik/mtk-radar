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


#: Captures are WebM (Playwright) or Matroska (FFmpeg recorder, M2); renders
#: are MP4. Declaring every file as MP4 mislabelled the review player's input.
_MEDIA_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
                ".mkv": "video/x-matroska", ".mov": "video/quicktime"}


def media_type_for(ref: str) -> str:
    return _MEDIA_TYPES.get(Path(str(ref).split("?", 1)[0]).suffix.lower(), "video/mp4")


def _serve_local(path: Path) -> FileResponse:
    # Starlette's FileResponse implements Range/If-Range and ETag handling, so
    # the browser can seek without this route re-implementing HTTP semantics.
    return FileResponse(
        path,
        media_type=media_type_for(path.name),
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
        media_type=media_type_for(ref),
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


#: G27 (evidence-to-video plan): schedule/package creation and media GC
#: serialize on THIS advisory lock. A sweep holds it (transaction-scoped) from
#: its second pin re-check through the deletions; a new schedule takes it
#: around the package INSERT. So a package can never gain a reference to a
#: render/cover artifact between the pin check and the file delete — the
#: classic mark-and-sweep race is closed instead of merely narrowed.
MEDIA_GC_LOCK_KEY = -7_324_118_204_335_577_601  # fixed signed bigint


async def _pinned_refs(conn) -> set[str]:
    """EVERY artifact ref string a live schedule can still need (G27).

    'Not just rows': distinct schedule rows may reference the SAME file
    (cover exported from a shared render, or several schedules on one
    render), so pinning is by ref VALUE as well as by row id. Anything a
    schedule that is not `cancelled` points at is pinned — including failed
    and paused (held) schedules: their evidence must survive for human
    review and the retry decision, and uncertain/owed uploads must not lose
    their artifacts.
    """
    rows = await conn.fetch(
        """
        SELECT DISTINCT ref FROM (
            SELECT r.video_path AS ref
            FROM renders r
            JOIN schedules s ON s.render_id = r.id
            WHERE s.state::text <> 'cancelled'
            UNION
            SELECT r.captions_path
            FROM renders r
            JOIN schedules s ON s.render_id = r.id
            WHERE s.state::text <> 'cancelled' AND r.captions_path IS NOT NULL
            UNION
            SELECT r.cover_path
            FROM renders r
            JOIN schedules s ON s.render_id = r.id
            WHERE s.state::text <> 'cancelled' AND r.cover_path IS NOT NULL
            UNION
            SELECT s.cover_path
            FROM schedules s
            WHERE s.state::text <> 'cancelled' AND s.cover_path IS NOT NULL
            UNION
            SELECT c.video_path
            FROM capture_sessions c
            JOIN renders r ON r.capture_id = c.id
            JOIN schedules s ON s.render_id = r.id
            WHERE s.state::text <> 'cancelled' AND c.video_path IS NOT NULL
        ) refs
        """
    )
    return {r["ref"] for r in rows}


async def _gc_candidates(pool, cutoff_days: int) -> list[dict[str, Any]]:
    """Artifacts past retention that are NOT pinned (G27 mark-and-sweep).

    A pin (exempt) is ANY live reference: a schedule in any state except
    `cancelled` — draft, needs_approval, approved, scheduled, published,
    failed, paused — pins its exact render row (and therefore ALL of that
    render's artifacts) plus its own cover file; captures behind pinned
    renders are pinned. References are matched by artifact ref string too,
    so a file shared between a pinned and an unpinned row survives.

    Legacy plain paths are returned as-is; managed refs (local://, s3://)
    carry their scheme. Accepts a pool OR a connection (the apply path runs
    the same query inside its lock-holding transaction for the second pin
    check).
    """
    rows = await pool.fetch(
        """
        WITH pinned_renders AS (
            -- ONLY a cancelled schedule releases its render; failed/paused/
            -- published/draft schedules all pin (G27).
            SELECT DISTINCT s.render_id AS id
            FROM schedules s
            WHERE s.render_id IS NOT NULL
              AND s.state::text <> 'cancelled'
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
        SELECT 'render_cover', r.id::text, r.cover_path, r.created_at
        FROM renders r
        WHERE r.created_at < now() - make_interval(days => $1)
          AND r.id NOT IN (SELECT id FROM pinned_renders)
          AND r.cover_path IS NOT NULL
        UNION ALL
        SELECT 'schedule_cover', s.id::text, s.cover_path, s.created_at
        FROM schedules s
        WHERE s.created_at < now() - make_interval(days => $1)
          AND s.state::text = 'cancelled'
          AND s.cover_path IS NOT NULL
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
    candidates = [dict(r) for r in rows]
    # Shared-file guard: even an unpinned ROW's artifact survives when the
    # SAME ref string is referenced by a pinned schedule/render (G27).
    pinned_refs = await _pinned_refs(pool)
    return [c for c in candidates if str(c["ref"]) not in pinned_refs]


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
    if body.dry_run:
        # Dry run = the MARK phase: list only. Nothing is touched, so no lock
        # is taken and concurrent scheduling is never delayed by a listing.
        candidates = await _gc_candidates(pool, body.retention_days)
        return {
            "mode": "dry_run", "retention_days": body.retention_days,
            "candidates": len(candidates),
            "items": [
                {"artifact": c["artifact"], "ref_id": c["ref_id"],
                 "ref": c["ref"], "created_at": str(c["created_at"])}
                for c in candidates
            ],
        }
    # APPLY (sweep) — G27 hardening, in ONE advisory-locked transaction:
    #   1. the lock serializes against schedule/package creation (any new pin
    #      waits for the sweep, and vice versa);
    #   2. the candidate set is RECOMPUTED inside the lock (second pin check)
    #      — anything pinned since the dry run, or by a concurrent commit
    #      before the lock was granted, silently drops out;
    #   3. retention age is the grace period: nothing newer than
    #      `retention_days` is ever touched, so an artifact under an active
    #      review/decision cannot be swept.
    deleted, failed = 0, []
    removed_refs: list[str] = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", MEDIA_GC_LOCK_KEY)
            candidates = await _gc_candidates(conn, body.retention_days)
            for c in candidates:
                ref = str(c["ref"])
                try:
                    if _delete_ref(ref):
                        deleted += 1
                        removed_refs.append(ref)
                except Exception as exc:  # noqa: BLE001 — one bad object never stops a GC run
                    failed.append({"ref": ref, "error": str(exc)[:300]})
            await conn.execute(
                "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
                "VALUES ($1, $2, $3, NULL, $4::jsonb)",
                "system:media_gc", "media:gc", "media",
                json.dumps({
                    "mode": "apply", "retention_days": body.retention_days,
                    "deleted": deleted, "failed": failed,
                    "removed_refs": removed_refs,
                }, default=str),
            )
    return {
        "mode": "apply", "retention_days": body.retention_days,
        "deleted": deleted, "failed": failed,
    }
