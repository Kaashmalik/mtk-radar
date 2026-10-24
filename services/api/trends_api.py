"""Trend radar API (v0.27 → v0.34 Trend Radar v2).

Turns the inbox into a scored, explainable topic radar. Scanning is explicit
(operator or the durable `trend_scan` job), idempotent by canonical URL, and
read-only with respect to offers: a trend is a proposal, never a verification.

v2 (enhancement plan 2026-10-24, WP-B): the scan is INCREMENTAL — items are
scored on arrival and a candidate with a stale `updated_at` is re-scored, so
every pass appends a `trend_observations` row. Velocity (score delta per hour,
EMA-smoothed) and corroboration (independent sources on the same story) become
real, capped, explainable demand inputs instead of "the item is old".
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import db
from api_hardening import effective_reviewer
from automation import guardrails as automation_guardrails
from automation_api import load_policy
from pagination import (
    decode_cursor,
    decode_datetime,
    decode_uuid,
    encode_cursor,
    set_next_cursor,
)
from settings_store import audit
from trend_engine import (
    apply_competitor_evidence,
    engagement_rate,
    radar_bands,
    score_item,
    smooth_velocity,
)

router = APIRouter(prefix="/trends", tags=["trends"])

#: A candidate is re-scored when its previous observation is older than this.
_RESCAN_AFTER_H = max(1, int(os.environ.get("MTK_TREND_RESCAN_H", "6")))
#: Healthy-scan re-arm interval for the durable `trend_scan` job.
_SCAN_INTERVAL_S = max(300, int(os.environ.get("MTK_TREND_SCAN_INTERVAL_S", "1800")))


class TrendStatusIn(BaseModel):
    status: str = Field(pattern="^(radar|shortlisted|promoted|dismissed)$")


class TrendScanResultIn(BaseModel):
    ok: bool
    detail: Optional[str] = Field(default=None, max_length=2000)


class CompetitorIn(BaseModel):
    channel: str = Field(min_length=1, max_length=120)
    subscribers: float = Field(ge=0)
    views_28d: float = Field(default=0, ge=0)


class CompetitorEvidenceIn(BaseModel):
    competitors: list[CompetitorIn] = Field(min_length=1, max_length=10)


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
    limit: int = Query(default=50, ge=1, le=200),
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
               score, velocity, peak_score::float8 AS peak_score, corroboration,
               score_reason::text AS score_reason, signals::text AS signals,
               engagement::text AS engagement,
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
    # P2 carry-over (system-review 2026-10-23): the summary counts used to be
    # page-local while reading as totals — a filtered first page undercounted
    # everything. The summary is now GLOBAL (one COUNT FILTER query);
    # `page_total` names what the page itself holds.
    global_summary = await pool.fetchrow(
        """
        SELECT COUNT(*)::int AS total,
               COUNT(*) FILTER (WHERE score >= 78)::int AS hot,
               COUNT(*) FILTER (WHERE status = 'shortlisted')::int AS shortlisted,
               COALESCE(AVG(score), 0)::float8 AS average_score
        FROM trend_candidates
        """
    )
    return {
        "candidates": candidates,
        "bands": radar_bands(candidates),
        "page_total": len(candidates),
        "summary": {
            "total": int(global_summary["total"]) if global_summary else len(candidates),
            "hot": int(global_summary["hot"]) if global_summary else 0,
            "shortlisted": int(global_summary["shortlisted"]) if global_summary else 0,
            "average_score": round(
                float(global_summary["average_score"]), 1
            ) if global_summary else 0.0,
        },
    }


@router.post("/scan", status_code=201)
async def scan_trends(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    """Score inbox items into the radar (idempotent on canonical URL).

    v2 incremental semantics: first-time items are scored once (and leave the
    unprocessed inbox); a candidate whose last observation is older than
    `_RESCAN_AFTER_H` is RE-SCORED, producing a `trend_observations` row that
    feeds velocity (score/hour) and the peak score. Re-scoring never marks the
    item unprocessed — it is still the same candidate URL.
    """
    pool = db.get()
    now = datetime.now(timezone.utc)
    rows = await pool.fetch(
        """
        SELECT i.id, i.url, i.canonical_url, i.title, i.observed_at, i.published_at,
               i.duplicate_group, i.story_key, i.text, i.selection,
               s.provider AS source_provider,
               s.category AS source_category, s.trust_tier::text AS trust_tier,
               s.country_scope,
               c.id AS candidate_id,
               c.score::float8 AS prev_score,
               c.velocity AS prev_velocity,
               c.peak_score::float8 AS prev_peak,
               c.updated_at AS prev_updated_at,
               (i.processed = FALSE) AS is_new_item
        FROM items i
        LEFT JOIN sources s ON s.id = i.source_id
        LEFT JOIN trend_candidates c ON c.url = COALESCE(i.canonical_url, i.url)
        WHERE i.processed = FALSE
           OR (c.id IS NOT NULL
               AND c.updated_at < now() - make_interval(hours => $2))
        ORDER BY COALESCE(i.published_at, i.observed_at) DESC
        LIMIT $1
        """,
        limit,
        _RESCAN_AFTER_H,
    )
    created = 0
    updated = 0
    rescored = 0
    scored_new_ids = []
    handled_candidates: set[uuid.UUID] = set()
    handled_urls: set[str] = set()
    for item in rows:
        data = dict(item)
        data["url"] = data.get("canonical_url") or data.get("url")
        if not data["url"]:
            continue
        if data["url"] in handled_urls or (
            data.get("candidate_id")
            and uuid.UUID(str(data["candidate_id"])) in handled_candidates
        ):
            # Same canonical URL observed by several inbox items: the first
            # row this pass already scored the candidate (the JOIN snapshot
            # predates the candidate this pass created). Only mark the
            # remaining items processed instead of double-inserting history.
            if data.get("is_new_item"):
                scored_new_ids.append(data["id"])
            continue
        handled_urls.add(data["url"])
        provider = data.get("source_provider") or ""
        existing_offers = await pool.fetchval(
            "SELECT COUNT(*) FROM offers WHERE provider ILIKE $1", f"%{provider}%"
        ) if provider else 0
        duplicates = 0
        corroborating = 1
        # G09: cluster by the STORY (normalized headline across URLs), falling
        # back to the canonical-URL group for rows that predate story_key.
        cluster = data.get("story_key") or data.get("duplicate_group")
        if cluster:
            duplicates = await pool.fetchval(
                "SELECT COUNT(*) FROM items "
                "WHERE COALESCE(story_key, duplicate_group) = $1",
                cluster,
            ) or 0
            corroborating = await pool.fetchval(
                """
                SELECT COUNT(DISTINCT s.provider)::int
                FROM items i2
                JOIN sources s ON s.id = i2.source_id
                WHERE COALESCE(i2.story_key, i2.duplicate_group) = $1
                  AND s.provider IS NOT NULL
                """,
                cluster,
            ) or 1
        corroborating = max(1, int(corroborating or 1))

        # G08: momentum = OBSERVED engagement growth (raw count deltas with
        # timestamps from source_observations). Unknown/flat engagement
        # bumps nothing — a retitle or an unchanged page can never fake a
        # rising trend via internal score movement.
        eng_rows = await pool.fetch(
            """
            SELECT observed_at, measurements
            FROM source_observations
            WHERE url = $1
            ORDER BY observed_at DESC
            LIMIT 6
            """,
            data["url"],
        )
        engagement = engagement_rate([
            (r["observed_at"], json.loads(r["measurements"]))
            for r in eng_rows
        ])
        scored = score_item(data, existing_offer_count=int(existing_offers or 0),
                            duplicate_count=max(0, int(duplicates or 0) - 1),
                            corroborating_sources=corroborating,
                            engagement=engagement)
        # Score-velocity is still RECORDED (a diagnostic of the candidate's
        # own re-scoring history), but it no longer moves demand.
        velocity = smooth_velocity(
            data.get("prev_score"), scored["score"], data.get("prev_updated_at"),
            now, data.get("prev_velocity") or 0.0,
        )
        scored["signals"]["velocity"] = round(velocity, 3)
        scored["signals"]["engagement"] = engagement
        peak = max(float(data.get("prev_peak") or 0.0), float(scored["score"]))
        row = await pool.fetchrow(
            """
            INSERT INTO trend_candidates
                (item_id, title, url, source_provider, source_category,
                 country_scope, language, demand_score, freshness_score,
                 feasibility_score, competition_gap, audience_fit, monetization,
                 score, velocity, peak_score, corroboration,
                 score_reason, signals, engagement, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15, $16, $17, $18::jsonb, $19::jsonb,
                    $20::jsonb, 'radar')
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
                velocity = EXCLUDED.velocity,
                peak_score = EXCLUDED.peak_score,
                corroboration = EXCLUDED.corroboration,
                score_reason = EXCLUDED.score_reason,
                signals = EXCLUDED.signals,
                engagement = EXCLUDED.engagement,
                updated_at = now()
            RETURNING id, (xmax = 0) AS inserted
            """,
            scored["item_id"], scored["title"], scored["url"],
            scored["source_provider"], scored["source_category"],
            scored["country_scope"], scored["language"], scored["demand_score"],
            scored["freshness_score"], scored["feasibility_score"],
            scored["competition_gap"], scored["audience_fit"],
            scored["monetization"], scored["score"],
            float(scored["signals"]["velocity"]), peak, corroborating,
            json.dumps(scored["score_reason"]), json.dumps(scored["signals"]),
            json.dumps(engagement, default=str),
        )
        if row["inserted"]:
            created += 1
        else:
            updated += 1
            if data.get("prev_updated_at") is not None:
                rescored += 1
        if row["id"]:
            handled_candidates.add(uuid.UUID(str(row["id"])))
        await pool.execute(
            """
            INSERT INTO trend_observations (candidate_id, score, velocity, sources)
            VALUES ($1, $2, $3, $4)
            """,
            row["id"], scored["score"],
            float(scored["signals"]["velocity"]), corroborating,
        )
        if data.get("is_new_item"):
            scored_new_ids.append(data["id"])

    # Processing an item IS its scoring (first time only). Re-scored
    # candidates stay processed; without this the newest inbox page was
    # re-scanned forever and the tail never reached the radar.
    if scored_new_ids:
        await pool.execute(
            "UPDATE items SET processed = TRUE WHERE id = ANY($1::uuid[])",
            scored_new_ids,
        )

    await audit(pool, actor="operator", action="trends:scan", entity="trend_candidates",
                detail={"created": created, "updated": updated, "rescored": rescored,
                        "scanned": len(rows), "processed": len(scored_new_ids)})
    return {
        "scanned": len(rows),
        "created": created,
        "updated": updated,
        "rescored": rescored,
        "processed": len(scored_new_ids),
        "rescan_after_h": _RESCAN_AFTER_H,
        "message": ("Radar refreshed — rising candidates carry a velocity "
                    "score; shortlist a lead, then verify it like any other offer."),
    }


@router.post("/scan-result")
async def trend_scan_result(result: TrendScanResultIn) -> dict:
    """The batch worker reports back after each `trend_scan` job claim.

    Same recurring-job contract as the collectors' poll-result: a healthy scan
    re-arms the job at `_SCAN_INTERVAL_S` with a fresh attempt budget; a failed
    scan retries in 300s and keeps its attempts, so 5 consecutive failures
    dead-letter it into operator attention (the cadence sweep in the batch
    worker stays as the fail-open fallback)."""
    pool = db.get()
    delay_s = _SCAN_INTERVAL_S if result.ok else 300
    await pool.execute(
        """
        INSERT INTO jobs (kind, payload, dedupe_key, max_attempts, run_after)
        VALUES ('trend_scan', '{}'::jsonb, 'trend_scan', 5,
                now() + make_interval(secs => $1::int))
        ON CONFLICT (dedupe_key) DO UPDATE
        SET status = CASE
                WHEN $2 THEN 'pending'
                WHEN jobs.attempts >= 5 THEN 'dead'
                ELSE 'pending' END,
            run_after = now() + make_interval(secs => $1::int),
            attempts = CASE WHEN $2 THEN 0 ELSE jobs.attempts END,
            last_error = $3,
            lease_holder = NULL, lease_expires_at = NULL, updated_at = now()
        """,
        delay_s, result.ok, (result.detail or None),
    )
    return {"rearmed": True, "ok": result.ok, "run_after_s": delay_s}


@router.post("/{trend_id}/competitors")
async def add_competitor_evidence(trend_id: uuid.UUID,
                                  body: CompetitorEvidenceIn) -> dict:
    """Record the operator's 3-competitor-rule research on a candidate.

    The 2026 playbook weights a topic by whether similar mid-size channels
    (10k-100k subscribers) get views above their subscriber count. The radar
    cannot scrape YouTube itself — the operator supplies the measured evidence
    and the engine bumps demand transparently, showing the new drivers and
    risks. A trend stays a proposal; verification still happens via offers.
    """
    pool = db.get()
    row = await pool.fetchrow(
        """
        SELECT id, demand_score, freshness_score, feasibility_score,
               competition_gap, audience_fit, monetization,
               score_reason::text AS score_reason, signals::text AS signals
        FROM trend_candidates WHERE id = $1
        """,
        trend_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="trend candidate not found")

    updated = apply_competitor_evidence(
        dict(row), [competitor.model_dump() for competitor in body.competitors])
    saved = await pool.fetchrow(
        """
        UPDATE trend_candidates SET
            demand_score = $2, score = $3,
            score_reason = $4::jsonb, signals = $5::jsonb, updated_at = now()
        WHERE id = $1
        RETURNING id, score, demand_score
        """,
        trend_id, updated["demand_score"], updated["score"],
        json.dumps(updated["score_reason"]), json.dumps(updated["signals"]),
    )
    await audit(pool, actor="operator", action="trend:competitor_evidence",
                entity="trend_candidates", entity_id=trend_id,
                detail={"channels": len(body.competitors),
                        "score": str(saved["score"])})
    return {
        "id": str(saved["id"]),
        "score": float(saved["score"]),
        "demand_score": float(saved["demand_score"]),
        "competitor_evidence": updated["signals"].get("competitor_evidence", {}),
        "why_now": updated["score_reason"].get("why_now", []),
        "risks": updated["score_reason"].get("risks", []),
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


class TrendPromoteIn(BaseModel):
    """Optional operator overrides at promotion time."""

    title: Optional[str] = Field(default=None, max_length=300)
    category: Optional[str] = Field(default=None, max_length=60)
    preset_fit: Optional[int] = Field(default=None, ge=0, le=100)
    kind: str = Field(default="timely", pattern="^(timely|evergreen)$")
    expires_at: Optional[str] = None  # ISO date/datetime string when set
    # EP-03 G18: the production track. explainer (default) = attributed
    # research content; 'offer' keeps the offer-centric eligibility/renewal
    # gates exactly as they were. `tested_tutorial`/`claim_walkthrough` keep
    # their human-capture gates downstream.
    content_type: str = Field(
        default="explainer",
        pattern="^(explainer|tested_tutorial|claim_walkthrough|offer)$")


@router.post("/{trend_id}/promote", status_code=201)
async def promote_trend(trend_id: uuid.UUID, body: TrendPromoteIn,
                        request: Request,
                        reviewer: Optional[str] = Query(default=None)) -> dict:
    """Promote a radar topic to the production queue (offer + row, one tx).

    Closes the radar dead-end: `promoted` used to be a status no endpoint
    could set, and scored topics needed manual re-finding in the inbox. This
    creates the offer-from-trend (state `candidate` — a proposal like any
    other, still requiring official verification evidence) AND its production
    queue row in ONE transaction, then marks the trend `promoted`. Every step
    is audited; human gates downstream are untouched.
    """
    import datetime as _dt

    import queue_api

    pool = db.get()
    # Same actor convention as the automation transitions in offers/schedules:
    # a reviewer token binds its human owner; a service credential may only
    # name an explicit automation:<stage> actor (never a human).
    actor = effective_reviewer(request, reviewer, default="operator")
    trend = await pool.fetchrow(
        """
        SELECT id, title, url, source_provider, source_category,
               score::float8 AS score, velocity, peak_score::float8 AS peak_score,
               corroboration, freshness_score::float8 AS freshness_score,
               status
        FROM trend_candidates WHERE id = $1
        """,
        trend_id,
    )
    if not trend:
        raise HTTPException(status_code=404, detail="trend candidate not found")
    existing = await pool.fetchval(
        "SELECT id::text FROM production_queue WHERE trend_id = $1", trend_id
    )
    if existing:
        raise HTTPException(status_code=409, detail="trend already on the production queue")

    expires_at = None
    if body.expires_at is not None:
        try:
            expires_at = _dt.datetime.fromisoformat(str(body.expires_at).replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422,
                                detail="expires_at must be an ISO date/datetime") from None

    # EP-03 G18: automation may only auto-shortlist a bounded number of
    # topics for research per day (the low-risk `auto_research_max_per_day`
    # guardrail). Counted in the same transaction behind an advisory lock so
    # concurrent automation promotions cannot race past the cap (same TOCTOU
    # defense as the approval budget in schedules_api). Human actors are
    # never capped.
    limit = None
    if actor.startswith(("automation:", "system:")):
        limits = automation_guardrails(await load_policy())
        limit = int(limits["auto_research_max_per_day"])
    snapshot = {
        "score": float(trend["score"]),
        "velocity": float(trend["velocity"] or 0.0),
        "peak_score": float(trend["peak_score"] or 0.0),
        "corroboration": int(trend["corroboration"] or 0),
        "url": str(trend["url"]),
    }
    async with pool.acquire() as conn:
        async with conn.transaction():
            if limit is not None:
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext('mtk-automation-research-budget'))")
                used = int(await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM audit_log
                    WHERE action = 'trend:promoted' AND actor LIKE 'automation:%'
                      AND created_at >= date_trunc('day', now())
                    """
                ) or 0)
                if used >= limit:
                    raise HTTPException(
                        status_code=429,
                        detail=(
                            "automation daily research budget exhausted "
                            f"({used}/{limit}) — raise auto_research_max_per_day "
                            "in Settings or promote manually"
                        ),
                    )
            offer = await conn.fetchrow(
                """
                INSERT INTO offers (title, provider, category, offer_type,
                                    redemption_url, state)
                VALUES ($1, $2, $3, 'trend_topic', $4, 'candidate')
                RETURNING id, state::text AS state
                """,
                body.title or trend["title"] or str(trend["url"]),
                trend["source_provider"] or "unknown",
                body.category or trend["source_category"] or "trend_signals",
                trend["url"],
            )
            queue_row = await conn.fetchrow(
                """
                INSERT INTO production_queue
                    (offer_id, trend_id, title, provider, category, kind,
                     preset_fit, trend_snapshot, expires_at, content_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
                RETURNING id
                """,
                offer["id"], trend["id"],
                body.title or trend["title"], trend["source_provider"],
                body.category or trend["source_category"],
                body.kind, body.preset_fit, _json(snapshot), expires_at,
                body.content_type,
            )
            # The trend becomes RESEARCH material, not an offer (G18): the
            # brief is version 1 of the versioned claim ledger — a starting
            # point a human editor builds on, never a verification. Promotion
            # cannot mean "verified": the offer stays a `candidate`.
            await conn.execute(
                """
                INSERT INTO research_briefs
                    (offer_id, version, content_type, viewer_question,
                     sources, auto_shortlisted)
                VALUES ($1, 1, $2, $3, $4::jsonb, $5)
                """,
                offer["id"], body.content_type,
                body.title or trend["title"],
                _json([{"url": str(trend["url"])}]) if trend["url"] else "[]",
                actor.startswith(("automation:", "system:")),
            )
            await conn.execute(
                "UPDATE trend_candidates SET status = 'promoted', updated_at = now() "
                "WHERE id = $1",
                trend_id,
            )
            await conn.execute(
                """
                INSERT INTO audit_log (actor, action, entity, entity_id, detail)
                VALUES ($1, 'trend:promoted', 'production_queue', $2, $3::jsonb)
                """,
                actor, queue_row["id"], _json({
                    "trend_id": str(trend["id"]),
                    "offer_id": str(offer["id"]),
                    "content_type": body.content_type,
                    "snapshot": snapshot,
                }),
            )
    return {
        "offer": {"id": str(offer["id"]), "state": offer["state"]},
        "queue_id": str(queue_row["id"]),
        "content_type": body.content_type,
        "trend": {"id": str(trend["id"]), "status": "promoted"},
        "message": ("Promoted to the production queue with a research brief "
                    "(version 1). The offer is still a candidate — verification "
                    "evidence decides nothing else."),
    }


def _json(value) -> str:
    return json.dumps(value, default=str)
