"""Trend radar API (v0.27).

Turns the inbox into a scored, explainable topic radar. Scanning is explicit
(operator or scheduler), idempotent by canonical URL, and read-only with
respect to offers: a trend is a proposal, never a verification.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

import db
from pagination import (
    decode_cursor,
    decode_datetime,
    decode_uuid,
    encode_cursor,
    set_next_cursor,
)
from settings_store import audit
from trend_engine import radar_bands, score_item

router = APIRouter(prefix="/trends", tags=["trends"])


class TrendStatusIn(BaseModel):
    status: str = Field(pattern="^(radar|shortlisted|promoted|dismissed)$")


def _decode(row) -> dict:
    item = dict(row)
    for key in ("score_reason", "signals"):
        value = item.get(key)
        if isinstance(value, str):
            try:
                item[key] = json.loads(value)
            except ValueError:
                item[key] = {}
    return item


@router.get("")
async def list_trends(
    response: Response,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: Optional[str] = Query(default=None),
) -> dict:
    pool = db.get()
    parts = decode_cursor(cursor, 3)
    try:
        # Keep the exact NUMERIC value: decoding to float and casting back can
        # round 59.28 up, so equal-score rows would never advance the cursor.
        before_score = Decimal(parts[0]) if parts else None
    except InvalidOperation:
        raise HTTPException(status_code=422, detail="invalid cursor: score") from None
    before_updated = decode_datetime(parts[1]) if parts else None
    before_id = decode_uuid(parts[2]) if parts else None
    rows = await pool.fetch(
        """
        SELECT id, item_id, title, url, source_provider, source_category,
               country_scope, language, demand_score, freshness_score,
               feasibility_score, competition_gap, audience_fit, monetization,
               score, score_reason::text AS score_reason, signals::text AS signals,
               status, created_at, updated_at
        FROM trend_candidates
        WHERE ($1::text IS NULL OR status = $1)
          AND ($3::numeric IS NULL
               OR (score, updated_at, id) < ($3::numeric, $4::timestamptz, $5::uuid))
        ORDER BY score DESC, updated_at DESC, id DESC
        LIMIT $2
        """,
        status,
        limit,
        before_score,
        before_updated,
        before_id,
    )
    candidates = [_decode(row) for row in rows]
    set_next_cursor(
        response, candidates, limit,
        lambda row: encode_cursor(row["score"], row["updated_at"], row["id"]),
    )
    return {
        "candidates": candidates,
        "bands": radar_bands(candidates),
        "summary": {
            "total": len(candidates),
            "hot": sum(1 for c in candidates if float(c["score"]) >= 78),
            "shortlisted": sum(1 for c in candidates if c["status"] == "shortlisted"),
            "average_score": round(
                sum(float(c["score"]) for c in candidates) / len(candidates), 1
            ) if candidates else 0,
        },
    }


@router.post("/scan", status_code=201)
async def scan_trends(limit: int = Query(default=100, le=500)) -> dict:
    """Score inbox items into the radar (idempotent on canonical URL)."""
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT i.id, i.url, i.canonical_url, i.title, i.observed_at, i.published_at,
               i.duplicate_group, s.provider AS source_provider,
               s.category AS source_category, s.trust_tier::text AS trust_tier,
               s.country_scope
        FROM items i
        LEFT JOIN sources s ON s.id = i.source_id
        WHERE i.processed = FALSE
        ORDER BY COALESCE(i.published_at, i.observed_at) DESC
        LIMIT $1
        """,
        limit,
    )
    created = 0
    updated = 0
    scored_ids = []
    for item in rows:
        data = dict(item)
        data["url"] = data.get("canonical_url") or data.get("url")
        if not data["url"]:
            continue
        provider = data.get("source_provider") or ""
        existing_offers = await pool.fetchval(
            "SELECT COUNT(*) FROM offers WHERE provider ILIKE $1", f"%{provider}%"
        ) if provider else 0
        duplicates = 0
        if data.get("duplicate_group"):
            duplicates = await pool.fetchval(
                "SELECT COUNT(*) FROM items WHERE duplicate_group = $1",
                data["duplicate_group"],
            ) or 0
        scored = score_item(data, existing_offer_count=int(existing_offers or 0),
                            duplicate_count=max(0, int(duplicates or 0) - 1))
        row = await pool.fetchrow(
            """
            INSERT INTO trend_candidates
                (item_id, title, url, source_provider, source_category,
                 country_scope, language, demand_score, freshness_score,
                 feasibility_score, competition_gap, audience_fit, monetization,
                 score, score_reason, signals, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15::jsonb, $16::jsonb, 'radar')
            ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                source_provider = EXCLUDED.source_provider,
                source_category = EXCLUDED.source_category,
                country_scope = EXCLUDED.country_scope,
                demand_score = EXCLUDED.demand_score,
                freshness_score = EXCLUDED.freshness_score,
                feasibility_score = EXCLUDED.feasibility_score,
                competition_gap = EXCLUDED.competition_gap,
                audience_fit = EXCLUDED.audience_fit,
                monetization = EXCLUDED.monetization,
                score = EXCLUDED.score,
                score_reason = EXCLUDED.score_reason,
                signals = EXCLUDED.signals,
                updated_at = now()
            RETURNING id, (xmax = 0) AS inserted
            """,
            scored["item_id"], scored["title"], scored["url"],
            scored["source_provider"], scored["source_category"],
            scored["country_scope"], scored["language"], scored["demand_score"],
            scored["freshness_score"], scored["feasibility_score"],
            scored["competition_gap"], scored["audience_fit"],
            scored["monetization"], scored["score"],
            json.dumps(scored["score_reason"]), json.dumps(scored["signals"]),
        )
        if row["inserted"]:
            created += 1
        else:
            updated += 1
        scored_ids.append(data["id"])

    # Scoring an item IS its processing. Without this the same newest `limit`
    # inbox rows were re-scanned forever and the tail never reached the radar.
    if scored_ids:
        await pool.execute(
            "UPDATE items SET processed = TRUE WHERE id = ANY($1::uuid[])",
            scored_ids,
        )

    await audit(pool, actor="operator", action="trends:scan", entity="trend_candidates",
                detail={"created": created, "updated": updated, "scanned": len(rows),
                        "processed": len(scored_ids)})
    return {
        "scanned": len(rows),
        "created": created,
        "updated": updated,
        "processed": len(scored_ids),
        "message": "Radar refreshed — shortlist a lead, then verify it like any other offer.",
    }


@router.patch("/{trend_id}")
async def set_trend_status(trend_id: uuid.UUID, body: TrendStatusIn) -> dict:
    pool = db.get()
    row = await pool.fetchrow(
        "UPDATE trend_candidates SET status = $2, updated_at = now() "
        "WHERE id = $1 RETURNING id, status",
        trend_id, body.status,
    )
    if not row:
        raise HTTPException(status_code=404, detail="trend candidate not found")
    await audit(pool, actor="operator", action=f"trend:{body.status}",
                entity="trend_candidates", entity_id=trend_id)
    return {"id": str(row["id"]), "status": row["status"]}
