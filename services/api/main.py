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
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import db
import api_hardening
from captures_api import router as captures_router
import health_api
from health_api import router as health_router
from locks_api import router as locks_router
from jsonb import decode_mapping
from normalize import canonicalize_url, hash_parts
from offers_api import router as offers_router
from platforms_api import router as platforms_router
from analytics_api import router as analytics_router
from renders_api import router as renders_router
from schedules_api import router as schedules_router
from settings_api import router as settings_router
from schemas import ItemIn, PollResult, SourceIn

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://mtk:mtk@localhost:5432/mtk_radar"
)

app = FastAPI(title="MTK RADAR AI API", version="0.22.0")
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
    for default in ("http://localhost:3000", "http://127.0.0.1:3000"):
        if default not in origins:
            origins.append(default)
    public = os.environ.get("MTK_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public and public not in origins:
        origins.append(public)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(offers_router)
app.include_router(captures_router)
app.include_router(renders_router)
app.include_router(schedules_router)
app.include_router(settings_router)
app.include_router(health_router)
app.include_router(locks_router)
app.include_router(platforms_router)
app.include_router(analytics_router)

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
async def list_sources(enabled: Optional[bool] = None) -> list[dict]:
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT id, provider, canonical_domain, account_handle, category, adapter,
               config, enabled, polling_cadence::text AS polling_cadence,
               country_scope, trust_tier::text AS trust_tier, last_checked_at
        FROM sources
        WHERE ($1::boolean IS NULL OR enabled = $1)
        ORDER BY trust_tier, provider
        """,
        enabled,
    )
    # `config` is jsonb — asyncpg hands it over as serialized JSON, so decode
    # it into a real object for API consumers (collectors read config.* keys).
    result = []
    for row in rows:
        source = dict(row)
        source["config"] = decode_mapping(source.get("config"))
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
    return {"id": row["id"], "created": True}


@app.post("/sources/{source_id}/poll-result")
async def poll_result(source_id: uuid.UUID, result: PollResult) -> dict:
    """Collectors report back after each poll → updates last_checked_at and health."""
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE sources
        SET last_checked_at = now(),
            config = config || $2::jsonb
        WHERE id = $1
        RETURNING id
        """,
        source_id,
        _json({"health": {"ok": result.ok, "detail": result.detail}}),
    )
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
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
    canonical = canonicalize_url(str(item.url))
    dupe_group = canonical
    text_hash = hash_parts(canonical, item.title, item.selection or item.text)

    row = await pool.fetchrow(
        """
        INSERT INTO items (source_id, external_item_id, url, canonical_url, title,
                           observed_at, published_at, text_hash, duplicate_group)
        VALUES ($1, $2, $3, $4, $5,
                COALESCE($6, now()), $7, $8, $9)
        ON CONFLICT (source_id, external_item_id) DO NOTHING
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

    # Conflict → fetch the existing candidate; canonical-URL collision still
    # counts as a duplicate for the inbox dedup view.
    existing = await pool.fetchrow(
        "SELECT id FROM items WHERE source_id = $1 AND external_item_id = $2",
        source_id,
        external_item_id,
    )
    return {
        "id": existing["id"] if existing else None,
        "created": False,
        "duplicate": True,
        "canonical_url": canonical,
    }


@app.get("/items")
async def list_items(
    processed: Optional[bool] = None,
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    """Review inbox — unprocessed candidates first (most recent)."""
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT i.id, i.url, i.canonical_url, i.title, i.observed_at, i.published_at,
               i.duplicate_group, i.processed,
               s.provider AS source_provider, s.category AS source_category,
               s.trust_tier::text AS trust_tier
        FROM items i
        LEFT JOIN sources s ON s.id = i.source_id
        WHERE ($1::boolean IS NULL OR i.processed = $1)
        ORDER BY i.observed_at DESC
        LIMIT $2
        """,
        processed,
        limit,
    )
    return [dict(r) for r in rows]


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
