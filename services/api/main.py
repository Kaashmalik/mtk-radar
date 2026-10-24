"""MTK RADAR AI — API service (FastAPI).

Single source of truth backend for offers, evidence, projects, and schedules.
Workers and the extension communicate with this API only.

Run locally:
    uvicorn main:app --reload --port 8000
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

import db
import api_hardening
from pagination import (
    decode_cursor,
    decode_datetime,
    decode_uuid,
    encode_cursor,
    set_next_cursor,
)
from attention_api import router as attention_router
from automation_api import router as automation_router
from costs_api import router as costs_router
from captures_api import router as captures_router
import health_api
from health_api import router as health_router
from jobs_api import router as jobs_router
from locks_api import router as locks_router
from media_api import router as media_router
from metrics_api import router as metrics_router
from jsonb import decode_mapping
import tos_review
from normalize import canonicalize_url, hash_parts
from offers_api import router as offers_router
from platforms_api import router as platforms_router
from analytics_api import router as analytics_router
from content_studio_api import router as studio_router
from renders_api import router as renders_router
from schedules_api import router as schedules_router
from settings_api import router as settings_router
from trends_api import router as trends_router
from queue_api import router as queue_router
from worker_health import router as workers_router
from upload_sessions_api import router as upload_sessions_router
from schemas import ItemIn, PollResult, SourceIn, TosReviewIn

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://mtk:mtk@localhost:5432/mtk_radar"
)

app = FastAPI(title="MTK RADAR AI API", version="0.30.0")
health_api.APP_VERSION = app.version


def _cors_origins() -> list[str]:
    """Browser origins allowed to call the API.

    The dashboard's client-side islands (identity, corrections, settings,
    connections, sources) are same-origin-agnostic: the browser enforces
    CORS. A hardcoded localhost list would break every real deployment
    (127.0.0.1, a domain, a reverse proxy), so the allowlist is
    configurable and seeded from the public base URL.
    """
    raw = os.environ.get("MTK_CORS_ORIGINS", "").strip()
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    public = os.environ.get("MTK_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public and public not in origins:
        origins.append(public)
    if not origins:
        # Dev fallback ONLY: an unconfigured deployment still needs the local
        # dashboard. Once any origin is configured, localhost is NOT silently
        # trusted alongside it — with allow_credentials=True a leftover dev
        # origin on a deployed host is a real exposure.
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Cursor pagination is unusable from a browser without this: the
    # dashboard cannot read a header the cross-origin allowlist hides.
    expose_headers=["X-Next-Cursor"],
)

app.include_router(offers_router)
app.include_router(captures_router)
app.include_router(renders_router)
app.include_router(schedules_router)
app.include_router(settings_router)
app.include_router(automation_router)
app.include_router(costs_router)
app.include_router(health_router)
app.include_router(locks_router)
app.include_router(jobs_router)
app.include_router(platforms_router)
app.include_router(analytics_router)
app.include_router(trends_router)
app.include_router(queue_router)
app.include_router(studio_router)
app.include_router(attention_router)
app.include_router(workers_router)
app.include_router(upload_sessions_router)
app.include_router(media_router)
app.include_router(metrics_router)

# Optional bearer-token auth (MTK_API_TOKEN, v0.13) + reviewer-token identity
# (v0.16) + structured request logging. Unset token = open local dev; set it
# for anything reachable beyond localhost.
api_hardening.register(app, db_url=DATABASE_URL)
app.include_router(api_hardening.router)


@app.on_event("startup")
async def startup() -> None:
    await db.init(DATABASE_URL)


@app.on_event("shutdown")
async def shutdown() -> None:
    await db.close()


# ---------------------------------------------------------------- health


# ---------------------------------------------------------------- sources


@app.get("/sources")
async def list_sources(
    response: Response,
    enabled: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    cursor: Optional[str] = Query(default=None),
) -> list[dict]:
    pool = db.get()
    parts = decode_cursor(cursor, 3)
    before_tier = parts[0] if parts else None
    before_provider = decode_datetime(parts[1]) if parts else None
    before_id = decode_uuid(parts[2]) if parts else None
    rows = await pool.fetch(
        """
        SELECT id, provider, canonical_domain, account_handle, category, adapter,
               config, enabled, polling_cadence::text AS polling_cadence,
               country_scope, trust_tier::text AS trust_tier, last_checked_at,
               tos_reviewed_at, tos_reviewer, tos_reference
        FROM sources
        WHERE ($1::boolean IS NULL OR enabled = $1)
          AND ($3::text IS NULL
               OR (trust_tier::text, provider, id) < ($3::text, $4::text, $5::uuid))
        ORDER BY trust_tier, provider, id
        LIMIT $2
        """,
        enabled,
        limit,
        before_tier,
        before_provider,
        before_id,
    )
    set_next_cursor(
        response, [dict(r) for r in rows], limit,
        lambda row: encode_cursor(row["trust_tier"], row["provider"], row["id"]),
    )
    # `config` is jsonb — asyncpg hands it over as serialized JSON, so decode
    # it into a real object for API consumers (collectors read config.* keys).
    result = []
    for row in rows:
        source = dict(row)
        source["config"] = decode_mapping(source.get("config"))
        # A review is a statement about terms at a point in time (slice 11).
        source["tos_expires_at"] = tos_review.expires_at(source.get("tos_reviewed_at"))
        source["tos_valid"] = tos_review.is_valid(source.get("tos_reviewed_at"))
        result.append(source)
    return result


@app.post("/sources", status_code=201)
async def create_source(source: SourceIn) -> dict:
    """Register a source. Idempotent on (provider, canonical_domain)."""
    pool = db.get()
    existing = await pool.fetchrow(
        "SELECT id FROM sources WHERE provider = $1 AND COALESCE(canonical_domain, '') = $2",
        source.provider,
        source.canonical_domain or "",
    )
    if existing:
        return {"id": existing["id"], "created": False}

    row = await pool.fetchrow(
        """
        INSERT INTO sources (provider, canonical_domain, account_handle, category,
                             adapter, config, polling_cadence, country_scope, trust_tier, enabled)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::text::interval, $8, $9::trust_tier, $10)
        RETURNING id
        """,
        source.provider,
        source.canonical_domain,
        source.account_handle,
        source.category,
        source.adapter,
        _json(source.config),
        source.polling_cadence,
        source.country_scope,
        source.trust_tier,
        source.enabled,
    )
    # Durable owed-work record: every enabled source owes recurring collection.
    # The collector claims these (v0.33); the list sweep remains the fallback.
    if source.enabled:
        await pool.execute(
            """
            INSERT INTO jobs (kind, entity_id, payload, dedupe_key, max_attempts, run_after)
            VALUES ('collect', $1, $2::jsonb, $3, 5, now())
            ON CONFLICT (dedupe_key) DO NOTHING
            """,
            row["id"],
            _json({"provider": source.provider, "adapter": source.adapter}),
            f"collect:{row['id']}",
        )
    return {"id": row["id"], "created": True}


@app.post("/sources/{source_id}/tos-review")
async def record_tos_review(source_id: uuid.UUID, review: TosReviewIn,
                            request: Request) -> dict:
    """Record a human decision that automated reading of this source is permitted.

    robots.txt is checked separately at fetch time; this is the contractual
    permission. The reviewer is bound from the authenticated token when present,
    otherwise the explicit body field is the recorded identity (service callers).
    Re-recording replaces the previous attestation; the audit log keeps history.
    """
    actor = api_hardening.effective_reviewer(request, review.reviewer, require=True)
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE sources
        SET tos_reviewed_at = clock_timestamp(), tos_reviewer = $2, tos_reference = $3
        WHERE id = $1
        RETURNING id, tos_reviewed_at, tos_reviewer, tos_reference
        """,
        source_id, actor, review.reference,
    )
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, 'sources', $3, $4::jsonb)",
        actor, "tos_review:recorded", source_id,
        _json({"reference": review.reference}),
    )
    return dict(row)


@app.delete("/sources/{source_id}/tos-review")
async def revoke_tos_review(source_id: uuid.UUID, request: Request,
                            reviewer: Optional[str] = Query(default=None)) -> dict:
    """Withdraw the permission to read a source (WP01 slice 11).

    Clearing the record stops new machine-collected evidence immediately; it does
    not rewrite evidence already stored, and reviewer-attested snapshots remain
    possible. The audit log records who withdrew it.
    """
    actor = api_hardening.effective_reviewer(request, reviewer, require=True)
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE sources
        SET tos_reviewed_at = NULL, tos_reviewer = NULL, tos_reference = NULL
        WHERE id = $1
        RETURNING id
        """,
        source_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, 'sources', $3, $4::jsonb)",
        actor, "tos_review:revoked", source_id, _json({}),
    )
    return {"id": row["id"], "revoked": True}


@app.post("/sources/{source_id}/poll-result")
async def poll_result(source_id: uuid.UUID, result: PollResult) -> dict:
    """Collectors report back after each poll → updates last_checked_at and health.

    A healthy poll also RE-ARMS the durable `collect` job with the source's
    cadence (the queue only wakes the collector when the next poll is due);
    a failed poll retries sooner. The cadence sweep stays as the fallback."""
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE sources
        SET last_checked_at = now(),
            config = config || $2::jsonb
        WHERE id = $1
        RETURNING id, enabled,
                  COALESCE(EXTRACT(epoch FROM polling_cadence)::int, 21600) AS cadence_s
        """,
        source_id,
        _json({"health": {"ok": result.ok, "detail": result.detail}}),
    )
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
    if row["enabled"]:
        # Recurring job contract: healthy poll → pending with the source's
        # cadence and a fresh attempt budget; failed poll → pending sooner,
        # keeping the attempt count so 5 consecutive failures dead-letter the
        # job into operator attention. The success path also clears any stale
        # claim lease, so a worker lost mid-poll cannot wedge the source.
        delay_s = row["cadence_s"] if result.ok else 300
        await pool.execute(
            """
            INSERT INTO jobs (kind, entity_id, payload, dedupe_key, max_attempts, run_after)
            VALUES ('collect', $1, '{}'::jsonb, $2, 5, now() + make_interval(secs => $3::int))
            ON CONFLICT (dedupe_key) DO UPDATE
            SET status = CASE
                    WHEN $4 THEN 'pending'
                    WHEN jobs.attempts >= 5 THEN 'dead'
                    ELSE 'pending' END,
                run_after = now() + make_interval(secs => $3::int),
                attempts = CASE WHEN $4 THEN 0 ELSE jobs.attempts END,
                last_error = $5,
                lease_holder = NULL, lease_expires_at = NULL, updated_at = now()
            """,
            source_id, f"collect:{source_id}", delay_s, result.ok,
            (result.detail or None),
        )
    return {"id": row["id"], "last_checked_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------- items (inbox)


@app.post("/items", status_code=201)
async def create_item(item: ItemIn) -> dict:
    """Ingest a candidate from a collector or the extension.

    Dedup guarantees (master plan §18 week 2): a candidate appears EXACTLY ONCE
    — keyed by (source_id, external_item_id) and by the canonical URL + text hash.
    Re-submissions return the existing item with `created: false, duplicate: true`.
    """
    pool = db.get()
    resolved = await _resolve_source_id(pool, item.source_id)
    if item.source_id is None:
        item.source_id = resolved
    source_id = item.source_id

    external_item_id = item.external_item_id or str(uuid.uuid4())
    try:
        canonical = canonicalize_url(str(item.url))
    except ValueError as exc:
        # a malformed port (e.g. https://host:abc/) raised out of urlsplit —
        # caller input, so a 4xx, never a 500
        raise HTTPException(status_code=422,
                            detail=f"unparseable item url: {exc}") from exc
    dupe_group = canonical
    text_hash = hash_parts(canonical, item.title, item.selection or item.text)

    row = await pool.fetchrow(
        """
        INSERT INTO items (source_id, external_item_id, url, canonical_url, title,
                           observed_at, published_at, text_hash, duplicate_group)
        VALUES ($1, $2, $3, $4, $5,
                COALESCE($6, now()), $7, $8, $9)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        source_id,
        external_item_id,
        str(item.url),
        canonical,
        item.title,
        item.observed_at,
        item.published_at,
        text_hash,
        dupe_group,
    )

    if row:
        return {"id": row["id"], "created": True, "duplicate": False, "canonical_url": canonical}

    # Conflict → fetch the existing candidate. `ON CONFLICT DO NOTHING` (no
    # target) covers BOTH documented keys: (source_id, external_item_id) and
    # the canonical-URL + text-hash pair enforced by the unique partial index
    # added in migration 031 — a resubmission with a fresh external_item_id no
    # longer creates a second row.
    existing = await pool.fetchrow(
        """
        SELECT id FROM items
        WHERE (source_id = $1 AND external_item_id = $2)
           OR (canonical_url = $3 AND text_hash = $4)
        ORDER BY observed_at
        LIMIT 1
        """,
        source_id,
        external_item_id,
        canonical,
        text_hash,
    )
    return {
        "id": existing["id"] if existing else None,
        "created": False,
        "duplicate": True,
        "canonical_url": canonical,
    }


@app.get("/items")
async def list_items(
    response: Response,
    processed: Optional[bool] = None,
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, le=200),
    cursor: Optional[str] = Query(default=None),
) -> list[dict]:
    """Review inbox — unprocessed candidates first (most recent).

    Paginated with an opaque keyset cursor so the inbox tail is reachable;
    a fixed LIMIT previously hid every item older than the newest page.
    `q` searches title and URL (inbox search/filter, plan §6 P0).
    """
    pool = db.get()
    parts = decode_cursor(cursor, 2)
    before_observed = decode_datetime(parts[0]) if parts else None
    before_id = decode_uuid(parts[1]) if parts else None
    rows = await pool.fetch(
        """
        SELECT i.id, i.url, i.canonical_url, i.title, i.observed_at, i.published_at,
               i.duplicate_group, i.processed,
               s.provider AS source_provider, s.category AS source_category,
               s.trust_tier::text AS trust_tier
        FROM items i
        LEFT JOIN sources s ON s.id = i.source_id
        WHERE ($1::boolean IS NULL OR i.processed = $1)
          AND ($5::text IS NULL OR i.title ILIKE '%' || $5 || '%'
               OR i.url ILIKE '%' || $5 || '%'
               OR coalesce(i.canonical_url, '') ILIKE '%' || $5 || '%')
          AND ($3::timestamptz IS NULL
               OR (i.observed_at, i.id) < ($3::timestamptz, $4::uuid))
        ORDER BY i.observed_at DESC, i.id DESC
        LIMIT $2
        """,
        processed,
        limit,
        before_observed,
        before_id,
        q,
    )
    out = [dict(r) for r in rows]
    set_next_cursor(
        response, out, limit,
        lambda row: encode_cursor(row["observed_at"], row["id"]),
    )
    return out


@app.patch("/items/{item_id}/processed")
async def mark_processed(item_id: uuid.UUID, processed: bool = True) -> dict:
    pool = db.get()
    row = await pool.fetchrow(
        "UPDATE items SET processed = $2 WHERE id = $1 RETURNING id",
        item_id,
        processed,
    )
    if not row:
        raise HTTPException(status_code=404, detail="item not found")
    return {"id": row["id"], "processed": processed}


# ---------------------------------------------------------------- helpers


async def _resolve_source_id(pool: asyncpg.Pool, source_id: Optional[uuid.UUID]) -> uuid.UUID:
    """Collectors pass their registered source. Extension saves resolve to (or
    create) the single 'browser-extension' Tier-B source."""
    if source_id is not None:
        row = await pool.fetchrow("SELECT id FROM sources WHERE id = $1", source_id)
        if not row:
            raise HTTPException(status_code=404, detail="source not found")
        return row["id"]

    row = await pool.fetchrow("SELECT id FROM sources WHERE adapter = 'extension' LIMIT 1")
    if row:
        return row["id"]

    # Only one creation race-winner matters; use advisory lock against races.
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(872341)")
            row = await conn.fetchrow("SELECT id FROM sources WHERE adapter = 'extension' LIMIT 1")
            if row:
                return row["id"]
            row = await conn.fetchrow(
                """
                INSERT INTO sources (provider, category, adapter, trust_tier, polling_cadence)
                VALUES ('Browser extension (saved links)', 'saved_links', 'extension',
                        'B_discovery_lead', '0 seconds')
                RETURNING id
                """
            )
            return row["id"]


def _json(value) -> str:
    import json

    return json.dumps(value, default=str)


# TODO(week-9): POST /schedules — schedule creation requires approved version hash.
