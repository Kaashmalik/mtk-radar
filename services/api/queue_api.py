"""Production queue (v0.35 — enhancement plan 2026-10-24, WP-C).

One ranked "videos to make" list. Rank is computed ON READ from stored,
recomputable components — never stored, because a stored rank silently drifts
from the evidence it ranks:

    rank = 0.35·trend + 0.30·evidence + 0.20·freshness + 0.15·fit

    trend      live trend-candidate score when the row was promoted from a
               trend (0 for offer-only rows; the trend snapshot keeps the
               promotion-time score for the record)
    evidence   G15: support that is CURRENT and INDEPENDENT — snapshot VOLUME
               counts for nothing. 0–100:
                 support       40 when fresh evidence comes from the
                               provider's own domain (`official`), 25 for
                               fresh third-party evidence, 0 when a row's
                               only support is stale snapshots
                 claims        30 × (declared required claims covered by
                               fresh evidence); if the offer declares no
                               claims, nothing is demonstrated → 0
                 independence  30 × min(1, distinct fresh-evidence sources / 2)
               "Fresh" = captured within EVIDENCE_FRESH_DAYS, robots-permitted
               and (when recorded) a 200 fetch — older snapshots are history,
               not support.
    freshness  the trend's freshness score; neutral 50 when unknown
    fit        preset fit set by the operator (0–100); neutral 50 when unset

SAFETY IS A HARD ELIGIBILITY GATE, not a rank input: a row whose offer is
`expired`, `corrected` or back in `evidence_needed` never appears as ready,
whatever its rank would be — only `candidate`, `verified`,
`approved_for_video` and `published` offers stay listed, so ordering can
never substitute for verification.

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

#: Evidence older than this is history, not current support (G15).
EVIDENCE_FRESH_DAYS = 14

#: Offers in these states are eligible to sit on the ready queue; anything
#: else (expired/corrected/demoted to evidence_needed) is a hard exclusion.
ELIGIBLE_OFFER_STATES = ("candidate", "verified", "approved_for_video", "published")

#: The offer fields a reviewer must be able to support with evidence (G15):
#: exactly the claims the offer DECLARES. Computed in SQL for recomputability.
_REQUIRED_CLAIMS_SQL = """
    array_remove(ARRAY[
        CASE WHEN o.promo_code IS NOT NULL THEN 'promo_code' END,
        CASE WHEN o.redemption_url IS NOT NULL THEN 'redemption_url' END,
        CASE WHEN o.eligibility <> '{}'::jsonb AND o.eligibility IS NOT NULL
             THEN 'eligibility' END,
        CASE WHEN o.value <> '{}'::jsonb AND o.value IS NOT NULL
             THEN 'value' END,
        CASE WHEN jsonb_array_length(o.claim_steps) > 0 THEN 'claim_steps' END
    ], NULL)
"""

#: Expression shared by every list query so the documented formula lives in
#: exactly one place. Aliases must match the returned column names.
_RANK_SQL = """
    ROUND(
        {trend:.2f} * COALESCE(t.score, 0)
      + {evidence:.2f} * COALESCE(ev.component, 0)
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

#: G17: the ranked projection + joins are ONE code path shared by the list
#: endpoint and the detail endpoint. The detail query used to re-derive the
#: rank with its own GROUP BY that omitted `t.freshness_score` and
#: `q.preset_fit` (and, after G15, the `ev` lateral the rank references) — a
#: guaranteed 500 at runtime that unit mocks could never catch. Both endpoints
#: now render the same subquery; only the outer filter differs. ``
#: `_RANKED_SELECT_READY` keeps the G15 list semantics (status 'ready' + hard
#: eligibility gate); `_RANKED_SELECT_ANY` exists so the DETAIL endpoint can
#: still answer for archived/demoted rows — showing WHY a row left the queue.
_RANKED_SELECT_TEMPLATE = """
        WITH ranked AS (
            SELECT q.id, q.offer_id, q.trend_id, q.title, q.provider, q.category,
                   q.kind, q.preset_fit, q.trend_snapshot::text AS trend_snapshot,
                   q.expires_at, q.rank_pinned, q.status, q.created_at, q.updated_at,
                   q.content_type,
                   o.state::text AS offer_state, o.expires_at AS offer_expires_at,
                   t.score::float8 AS trend_score,
                   t.freshness_score::float8 AS trend_freshness,
                   t.velocity, t.corroboration,
                   (SELECT COUNT(*)::int FROM evidence e
                     WHERE e.offer_id = q.offer_id)
                     AS evidence_count,
                   CASE WHEN COALESCE(ev.fresh_count, 0) > 0 THEN true
                        ELSE false END AS has_current_evidence,
                   COALESCE(ev.component, 0) AS evidence_score,
                   ({_RANK_SQL}) AS rank,
                   ({_ORDER_SQL}) AS order_val
            FROM production_queue q
            LEFT JOIN offers o ON o.id = q.offer_id
            LEFT JOIN trend_candidates t ON t.id = q.trend_id
            LEFT JOIN LATERAL (
                SELECT {_REQUIRED_CLAIMS_SQL} AS required
            ) req ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*)::int AS fresh_count,
                    BOOL_OR(e.official) AS has_official,
                    COUNT(DISTINCT e.source_id)::int AS independent,
                    CASE WHEN COUNT(*) = 0 THEN 0::numeric
                    ELSE ROUND(
                          (CASE WHEN BOOL_OR(e.official) THEN 40.0 ELSE 25.0 END)
                        + 30.0 * CASE WHEN cardinality(req.required) = 0
                                 THEN 0.0
                                 ELSE LEAST(1.0,
                                      (SELECT COUNT(DISTINCT fld)::numeric
                                       FROM evidence e2
                                       CROSS JOIN LATERAL jsonb_array_elements_text(
                                           COALESCE(e2.supported_fields, '[]'::jsonb)
                                       ) AS fld
                                       WHERE e2.offer_id = q.offer_id
                                         AND e2.captured_at
                                             > now() - make_interval(
                                                   days => {EVIDENCE_FRESH_DAYS})
                                         AND COALESCE(e2.robots_allowed, TRUE)
                                         AND (e2.fetch_status IS NULL
                                              OR e2.fetch_status = 200)
                                         AND fld = ANY (req.required))
                                      / cardinality(req.required))
                                 END
                        + 30.0 * LEAST(1.0,
                              COUNT(DISTINCT e.source_id)::numeric / 2.0)
                    , 2) END AS component
                FROM evidence e
                WHERE e.offer_id = q.offer_id
                  AND e.captured_at > now() - make_interval(days => {EVIDENCE_FRESH_DAYS})
                  AND COALESCE(e.robots_allowed, TRUE)
                  AND (e.fetch_status IS NULL OR e.fetch_status = 200)
            ) ev ON TRUE
            WHERE {_VISIBILITY_SQL}
        )
"""

_RANKED_SELECT_READY = _RANKED_SELECT_TEMPLATE.format(
    _RANK_SQL=_RANK_SQL,
    _ORDER_SQL=_ORDER_SQL,
    _REQUIRED_CLAIMS_SQL=_REQUIRED_CLAIMS_SQL,
    EVIDENCE_FRESH_DAYS=EVIDENCE_FRESH_DAYS,
    ELIGIBLE_OFFER_STATES=ELIGIBLE_OFFER_STATES,
    _VISIBILITY_SQL=(
        "q.status = 'ready'\n"
        "              -- G15: safety is a hard eligibility gate, not a rank input.\n"
        "              AND (o.id IS NULL OR o.state::text IN "
        + repr(ELIGIBLE_OFFER_STATES) + ")"),
)
_RANKED_SELECT_ANY = _RANKED_SELECT_TEMPLATE.format(
    _RANK_SQL=_RANK_SQL,
    _ORDER_SQL=_ORDER_SQL,
    _REQUIRED_CLAIMS_SQL=_REQUIRED_CLAIMS_SQL,
    EVIDENCE_FRESH_DAYS=EVIDENCE_FRESH_DAYS,
    ELIGIBLE_OFFER_STATES=ELIGIBLE_OFFER_STATES,
    _VISIBILITY_SQL="TRUE",
)


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
        _RANKED_SELECT_READY + """
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
                "content_type": row["content_type"],
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
                "evidence_score": float(row["evidence_score"] or 0),
                "has_current_evidence": row["has_current_evidence"],
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
    """Detail for one row (any status) with the SAME rank math as the list.

    G17: recomputes the rank through the shared ranked subquery instead of a
    hand-rolled GROUP BY that omitted joined columns and 500'd in production
    SQL — the list and the detail can never disagree about a rank again.
    """
    pool = db.get()
    row = await pool.fetchrow(
        _RANKED_SELECT_ANY + """
        SELECT * FROM ranked WHERE id = $1
        """,
        row_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="queue row not found")
    rank = float(row["rank"]) if row["rank"] is not None else None
    order_val = float(row["order_val"]) if row["order_val"] is not None else None
    return {
        "id": str(row["id"]),
        "offer_id": str(row["offer_id"]) if row["offer_id"] else None,
        "trend_id": str(row["trend_id"]) if row["trend_id"] else None,
        "title": row["title"],
        "provider": row["provider"],
        "category": row["category"],
        "kind": row["kind"],
        "content_type": row["content_type"],
        "preset_fit": row["preset_fit"],
        "trend_snapshot": row["trend_snapshot"],
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else
                      (row["offer_expires_at"].isoformat()
                       if row["offer_expires_at"] else None),
        "offer_state": row["offer_state"],
        "trend_score": row["trend_score"],
        "trend_freshness": row["trend_freshness"],
        "velocity": row["velocity"],
        "corroboration": row["corroboration"],
        "evidence_count": row["evidence_count"] or 0,
        "evidence_score": float(row["evidence_score"] or 0),
        "has_current_evidence": row["has_current_evidence"],
        "rank_pinned": row["rank_pinned"],
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "rank": rank,
        # readiness = the list's own gate: a row may exist in ANY status, but
        # `ready_now` answers "does it qualify for the ready list right now"
        # under the same G15 eligibility rule (expired/corrected/demoted
        # offers never count as ready, whatever their rank).
        "ready_now": row["status"] == "ready" and (
            row["offer_id"] is None or row["offer_state"] in ELIGIBLE_OFFER_STATES),
        "_order_val": order_val,
    }


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
                -- G16: cooling duration is measured from the last MEANINGFUL
                -- growth, never from the last observation — a rescan cadence
                -- keeps observations fresh but cannot reset a cooling trend.
                WITH latest AS (
                    SELECT DISTINCT ON (candidate_id)
                        candidate_id, velocity
                    FROM trend_observations
                    ORDER BY candidate_id, observed_at DESC
                ),
                last_growth AS (
                    SELECT DISTINCT ON (candidate_id)
                        candidate_id, observed_at AS last_growth_at
                    FROM trend_observations
                    WHERE velocity > 0
                    ORDER BY candidate_id, observed_at DESC
                ),
                first_seen AS (
                    SELECT candidate_id, MIN(observed_at) AS first_at
                    FROM trend_observations
                    GROUP BY candidate_id
                ),
                cooling AS (
                    SELECT l.candidate_id,
                           COALESCE(g.last_growth_at, f.first_at)
                               AS cooling_since,
                           l.velocity AS latest_velocity
                    FROM latest l
                    LEFT JOIN last_growth g ON g.candidate_id = l.candidate_id
                    LEFT JOIN first_seen f ON f.candidate_id = l.candidate_id
                ),
                dead AS (
                    SELECT q.id
                    FROM production_queue q
                    JOIN cooling c ON c.candidate_id = q.trend_id
                    WHERE q.status = 'ready'
                      AND c.latest_velocity <= 0
                      AND c.cooling_since < now() - interval '7 days'
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
