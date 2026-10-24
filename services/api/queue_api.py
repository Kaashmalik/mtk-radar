"""Production queue (v0.35 — enhancement plan 2026-10-24, WP-C).

One ranked "videos to make" list. Rank is computed ON READ from stored,
recomputable components — never stored, because a stored rank silently drifts
from the evidence it ranks:

    rank = 0.35·trend + 0.30·evidence + 0.20·freshness + 0.15·fit

    trend      live trend-candidate score when the row was promoted from a
               trend (0 for offer-only rows; the trend snapshot keeps the
               promotion-time score for the record)
    evidence   min(100, 25 × evidence snapshots attached to the offer)
    freshness  the trend's freshness score; neutral 50 when unknown
    fit        preset fit set by the operator (0–100); neutral 50 when unset

Every weight is visible here and in the dashboard legend. A queue row is a
proposal: verification (official evidence), capture recording, redaction
review and publish approval remain exactly where they were.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import db
from api_hardening import effective_reviewer
from pagination import decode_cursor, decode_uuid, encode_cursor, set_next_cursor
from settings_store import audit

router = APIRouter(tags=["queue"])

RANK_WEIGHTS = {"trend": 0.35, "evidence": 0.30, "freshness": 0.20, "fit": 0.15}

#: Expression shared by every list query so the documented formula lives in
#: exactly one place. Aliases must match the returned column names.
_RANK_SQL = """
    ROUND(
        {trend:.2f} * COALESCE(t.score, 0)
      + {evidence:.2f} * LEAST(100, 25 * COUNT(e.id))
      + {freshness:.2f} * COALESCE(t.freshness_score, 50)
      + {fit:.2f} * COALESCE(q.preset_fit, 50)
    , 2)
""".format(**RANK_WEIGHTS)


class QueueArchiveIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class QueueReorderIn(BaseModel):
    """Operator override: the exact ready-row order, first = top."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


# One monotonically decreasing order value so the whole list (pins + rank) is
# a single keyset: pinned rows map above every rank (1e6 - pin), unpinned rows
# use their computed rank. Deterministic and recomputable.
_ORDER_SQL = """
    CASE WHEN q.rank_pinned IS NOT NULL
         THEN 1000000 - q.rank_pinned
         ELSE {_RANK_SQL} END
""".format(_RANK_SQL=_RANK_SQL)


@router.get("/production-queue")
async def list_production_queue(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
) -> dict:
    """The ranked "videos to make" list (keyset-paginated, archived excluded).

    Order: operator pins first (ascending `rank_pinned`), then computed rank.
    """
    pool = db.get()
    parts = decode_cursor(cursor, 2)
    before_order = float(parts[0]) if parts else None
    before_id = decode_uuid(parts[1]) if parts else None

    rows = await pool.fetch(
        f"""
        WITH ranked AS (
            SELECT q.id, q.offer_id, q.trend_id, q.title, q.provider, q.category,
                   q.kind, q.preset_fit, q.trend_snapshot::text AS trend_snapshot,
                   q.expires_at, q.rank_pinned, q.status, q.created_at, q.updated_at,
                   o.state::text AS offer_state, o.expires_at AS offer_expires_at,
                   t.score::float8 AS trend_score,
                   t.freshness_score::float8 AS trend_freshness,
                   t.velocity, t.corroboration,
                   (SELECT COUNT(*)::int FROM evidence e
                     WHERE e.offer_id = q.offer_id)
                     AS evidence_count,
                   ({_RANK_SQL}) AS rank,
                   ({_ORDER_SQL}) AS order_val
            FROM production_queue q
            LEFT JOIN offers o ON o.id = q.offer_id
            LEFT JOIN trend_candidates t ON t.id = q.trend_id
            LEFT JOIN evidence e ON e.offer_id = q.offer_id
            WHERE q.status = 'ready'
            GROUP BY q.id, o.state, o.expires_at, t.score, t.freshness_score,
                     t.velocity, t.corroboration
        )
        SELECT * FROM ranked
        WHERE ($2::float8 IS NULL OR (order_val, id) < ($2::float8, $3::uuid))
        ORDER BY order_val DESC, id DESC
        LIMIT $1
        """,
        limit,
        before_order,
        before_id,
    )
    set_next_cursor(
        response, rows, limit,
        lambda row: encode_cursor(float(row["order_val"]), row["id"]),
    )
    return {
        "queue": [
            {
                "id": str(row["id"]),
                "offer_id": str(row["offer_id"]) if row["offer_id"] else None,
                "trend_id": str(row["trend_id"]) if row["trend_id"] else None,
                "title": row["title"],
                "provider": row["provider"],
                "category": row["category"],
                "kind": row["kind"],
                "offer_state": row["offer_state"],
                "expires_at": row["expires_at"].isoformat() if row["expires_at"] else
                              (row["offer_expires_at"].isoformat()
                               if row["offer_expires_at"] else None),
                "trend_snapshot": row["trend_snapshot"],
                "trend_score": row["trend_score"],
                "trend_freshness": row["trend_freshness"],
                "velocity": row["velocity"],
                "corroboration": row["corroboration"],
                "evidence_count": row["evidence_count"] or 0,
                "preset_fit": row["preset_fit"],
                "rank_pinned": row["rank_pinned"],
                "rank": float(row["rank"]),
                "status": row["status"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
            }
            for row in rows
        ]
    }


@router.post("/queue/{row_id}/archive")
async def archive_queue_row(row_id: uuid.UUID, body: QueueArchiveIn,
                            request: Request) -> dict:
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE production_queue
        SET status = 'archived', archived_reason = $2, updated_at = now()
        WHERE id = $1 AND status = 'ready'
        RETURNING id, status
        """,
        row_id, body.reason,
    )
    if not row:
        raise HTTPException(status_code=404,
                            detail="queue row not found (or already archived)")
    await audit(pool, actor=effective_reviewer(request, None, default="reviewer"),
                action="queue:archive", entity="production_queue", entity_id=row_id,
                detail={"reason": body.reason})
    return {"id": str(row["id"]), "status": row["status"]}


@router.post("/queue/reorder")
async def reorder_queue(body: QueueReorderIn, request: Request) -> dict:
    """Pin the operator's chosen order. Ids not in the list lose their pin
    (they fall back to the computed rank)."""
    pool = db.get()
    actor = effective_reviewer(request, None, default="reviewer")
    pinned: list[uuid.UUID] = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE production_queue SET rank_pinned = NULL "
                               "WHERE status = 'ready'")
            for position, row_id in enumerate(body.ids, start=1):
                updated = await conn.execute(
                    "UPDATE production_queue SET rank_pinned = $2, updated_at = now() "
                    "WHERE id = $1 AND status = 'ready'",
                    row_id, position,
                )
                if updated == "UPDATE 0":
                    raise HTTPException(
                        status_code=404,
                        detail=f"queue row {row_id} not found (or not ready)")
                pinned.append(row_id)
    for position, row_id in enumerate(pinned, start=1):
        await audit(pool, actor=actor, action="queue:reorder",
                    entity="production_queue", entity_id=row_id,
                    detail={"position": position})
    return {"pinned": len(pinned)}


@router.get("/queue/{row_id}")
async def get_queue_row(row_id: uuid.UUID) -> dict:
    pool = db.get()
    row = await pool.fetchrow(
        f"""
        SELECT q.*, o.state::text AS offer_state,
               t.score::float8 AS trend_score,
               t.velocity, t.corroboration,
               {_RANK_SQL} AS rank
        FROM production_queue q
        LEFT JOIN offers o ON o.id = q.offer_id
        LEFT JOIN trend_candidates t ON t.id = q.trend_id
        LEFT JOIN evidence e ON e.offer_id = q.offer_id
        WHERE q.id = $1
        GROUP BY q.id, o.state, t.score, t.velocity, t.corroboration
        """,
        row_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="queue row not found")
    return dict(row)


@router.post("/production-queue/expire")
async def expire_production_queue(request: Request) -> dict:
    """Self-archive stale rows (batch worker cadence). Deterministic reasons:

    - ``offer_expired``   the linked offer is expired
    - ``deadline_passed`` the row's own freshness deadline passed
    - ``trend_cooled``    the linked trend's latest observation is negative
                          velocity and older than 7 days

    The worker decides WHEN; this endpoint decides WHETHER — the same split
    as every automation step.
    """
    pool = db.get()
    actor = effective_reviewer(request, None, default="svc")
    async with pool.acquire() as conn:
        async with conn.transaction():
            offer_expired = await conn.fetch(
                """
                WITH dead AS (
                    SELECT q.id
                    FROM production_queue q
                    JOIN offers o ON o.id = q.offer_id
                    WHERE q.status = 'ready' AND o.state = 'expired'
                    FOR UPDATE OF q SKIP LOCKED
                )
                UPDATE production_queue q
                SET status = 'archived', archived_reason = 'offer_expired',
                    updated_at = now()
                FROM dead WHERE q.id = dead.id
                RETURNING q.id
                """,
            )
            deadline_passed = await conn.fetch(
                """
                WITH dead AS (
                    SELECT q.id
                    FROM production_queue q
                    WHERE q.status = 'ready' AND q.expires_at IS NOT NULL
                          AND q.expires_at < now()
                    FOR UPDATE OF q SKIP LOCKED
                )
                UPDATE production_queue q
                SET status = 'archived', archived_reason = 'deadline_passed',
                    updated_at = now()
                FROM dead WHERE q.id = dead.id
                RETURNING q.id
                """,
            )
            trend_cooled = await conn.fetch(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (o1.candidate_id)
                        o1.candidate_id, o1.velocity, o1.observed_at
                    FROM trend_observations o1
                    ORDER BY o1.candidate_id, o1.observed_at DESC
                ),
                dead AS (
                    SELECT q.id
                    FROM production_queue q
                    JOIN latest l ON l.candidate_id = q.trend_id
                    WHERE q.status = 'ready'
                      AND l.velocity <= 0
                      AND l.observed_at < now() - interval '7 days'
                    FOR UPDATE OF q SKIP LOCKED
                )
                UPDATE production_queue q
                SET status = 'archived', archived_reason = 'trend_cooled',
                    updated_at = now()
                FROM dead WHERE q.id = dead.id
                RETURNING q.id
                """,
            )
            archived = offer_expired or deadline_passed or trend_cooled
    counts = {
        "offer_expired": len(offer_expired),
        "deadline_passed": len(deadline_passed),
        "trend_cooled": len(trend_cooled),
    }
    if archived:
        await audit(pool, actor=actor, action="queue:auto_expire",
                    entity="production_queue", detail=counts)
    return {"expired": sum(counts.values()), "reasons": counts}
