"""Analytics router (week 12, master plan §7 "Analytics and scale").

Aggregate, read-only metrics to prioritize topics and improve packaging —
never to weaken verification. One endpoint, pure SQL aggregates:
  - pipeline funnel: inbox items → offers by state
  - verification load: evidence depth, corrections, recheck backlog
  - publishing health: schedules by state/platform, auto-pauses, failures
  - source freshness: last-poll age per enabled source
  - platform account / token health
"""

import json

from fastapi import APIRouter

import db

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _rows(pool, query: str):
    return [dict(r) for r in await pool.fetch(query)]


@router.get("")
async def analytics() -> dict:
    pool = db.get()

    funnel = await _rows(pool, "SELECT COUNT(*) AS n FROM items")
    offers_by_state = await _rows(
        "SELECT state::text AS state, COUNT(*) AS n FROM offers GROUP BY state ORDER BY n DESC"
    )
    verification = await pool.fetchrow(
        """
        SELECT
          (SELECT COUNT(*) FROM offers WHERE state IN ('verified','approved_for_video','published')) AS live_offers,
          (SELECT COUNT(*) FROM offers WHERE state IN ('expired','corrected')) AS retired_offers,
          (SELECT COUNT(*) FROM offer_corrections) AS corrections,
          (SELECT COUNT(*)::float / NULLIF((SELECT COUNT(DISTINCT offer_id) FROM evidence), 0)
             FROM evidence) AS evidence_per_offer,
          (SELECT COUNT(*) FROM offers
             WHERE state IN ('verified','approved_for_video','published')
               AND recheck_at <= now()) AS recheck_due
        """
    )
    schedules_by_state = await _rows(
        "SELECT state::text AS state, COUNT(*) AS n FROM schedules GROUP BY state ORDER BY n DESC"
    )
    schedules_by_platform = await _rows(
        """
        SELECT platform, state::text AS state, COUNT(*) AS n
        FROM schedules GROUP BY platform, state ORDER BY platform, state
        """
    )
    publishing = await pool.fetchrow(
        """
        SELECT
          (SELECT COUNT(*) FROM schedules WHERE state = 'published') AS published,
          (SELECT COUNT(*) FROM schedules WHERE state = 'failed') AS failed,
          (SELECT COUNT(*) FROM schedules WHERE state = 'paused') AS paused,
          (SELECT COUNT(*) FROM schedules
             WHERE outcome_detail->>'auto_paused' = 'true') AS auto_paused
        """
    )
    source_freshness = await _rows(
        """
        SELECT s.id, s.name, s.provider, s.enabled,
               s.last_checked_at,
               EXTRACT(EPOCH FROM (now() - s.last_checked_at))/3600.0 AS hours_since_poll,
               (SELECT COUNT(*) FROM items i WHERE i.source_id = s.id) AS item_count
        FROM sources s
        ORDER BY s.enabled DESC, hours_since_poll NULLS FIRST
        """
    )
    account_health = await _rows(
        "SELECT platform, status, expires_at, last_error FROM platform_accounts "
        "ORDER BY platform, status"
    )

    generated_at = await pool.fetchval("SELECT now()")

    return {
        "items_total": funnel[0]["n"] if funnel else 0,
        "offers_by_state": offers_by_state,
        "verification": dict(verification or {}),
        "schedules_by_state": schedules_by_state,
        "schedules_by_platform": schedules_by_platform,
        "publishing": dict(publishing or {}),
        "source_freshness": source_freshness,
        "account_health": account_health,
        "generated_at": generated_at,
    }
