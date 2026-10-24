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
from cache import ANALYTICS_KEY, cache_get_json, cache_set_json
from growth_engine import summarize as growth_summarize

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _rows(pool, query: str):
    return [dict(r) for r in await pool.fetch(query)]


@router.get("")
async def analytics() -> dict:
    pool = db.get()

    # v0.22: the aggregate read is the one hot path the dashboard hits on
    # every refresh — serve it from the optional Redis cache when available.
    # A cache miss, an unreachable Redis or a disabled cache all fall through
    # to a fresh computation.
    cached = await cache_get_json(ANALYTICS_KEY)
    if cached is not None:
        cached["cached"] = True
        return cached

    funnel = await _rows(pool, "SELECT COUNT(*) AS n FROM items")
    offers_by_state = await _rows(
        pool, "SELECT state::text AS state, COUNT(*) AS n FROM offers GROUP BY state ORDER BY n DESC"
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
        pool, "SELECT state::text AS state, COUNT(*) AS n FROM schedules GROUP BY state ORDER BY n DESC"
    )
    schedules_by_platform = await _rows(
        pool,
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
    rendering = await pool.fetchrow(
        """
        SELECT
          COUNT(*)::int AS total,
          COUNT(*) FILTER (WHERE status = 'rendered' AND qc_status = 'passed')::int
            AS qc_passed,
          COUNT(*) FILTER (WHERE status = 'qc_failed')::int AS qc_failed,
          COUNT(*) FILTER (WHERE status = 'render_failed')::int AS render_failed,
          COUNT(*) FILTER (WHERE COALESCE(qc_status, 'not_checked') = 'not_checked')::int
            AS not_checked,
          MAX(created_at) AS last_render_at
        FROM renders
        """
    )
    source_freshness = await _rows(
        pool,
        """
        SELECT s.id, COALESCE(s.canonical_domain, s.provider) AS name, s.provider, s.enabled,
               s.last_checked_at,
               (EXTRACT(EPOCH FROM (now() - s.last_checked_at)) / 3600.0)::double precision
                 AS hours_since_poll,
               (SELECT COUNT(*) FROM items i WHERE i.source_id = s.id) AS item_count
        FROM sources s
        ORDER BY s.enabled DESC, hours_since_poll NULLS FIRST
        """
    )
    account_health = await _rows(
        pool,
        "SELECT platform, status, expires_at, last_error FROM platform_accounts "
        "ORDER BY platform, status"
    )

    # ---- audience reach (v0.18): latest metrics snapshot per published post.
    metrics_totals = await pool.fetchrow(
        """
        WITH latest AS (
          SELECT DISTINCT ON (pm.schedule_id)
                 pm.schedule_id, pm.views, pm.likes, pm.comments, pm.impressions,
                 pm.avg_watch_s, pm.ctr, pm.avg_view_duration_s,
                 pm.avg_view_percentage, pm.retention_3s, pm.retention_3s_estimated,
                 pm.link_clicks, pm.subscribers_gained, pm.captured_at
          FROM post_metrics pm
          JOIN schedules s ON s.id = pm.schedule_id AND s.state = 'published'
          ORDER BY pm.schedule_id, pm.captured_at DESC
        )
        -- SUM without COALESCE: no measured value and a measured zero are
        -- different facts. The dashboard renders null as unavailable.
        SELECT COUNT(*)::int AS posts_measured,
               SUM(views)::bigint AS views,
               SUM(likes)::bigint AS likes,
               SUM(comments)::bigint AS comments,
               SUM(impressions)::bigint AS impressions,
               SUM(link_clicks)::bigint AS link_clicks,
               SUM(subscribers_gained)::bigint AS subscribers_gained,
               AVG(ctr)::double precision AS avg_ctr,
               AVG(retention_3s)::double precision AS avg_retention_3s,
               COUNT(*) FILTER (WHERE retention_3s_estimated)::int
                 AS posts_with_estimated_retention,
               MAX(captured_at) AS last_captured_at,
               (SELECT COUNT(*) FROM schedules WHERE state = 'published')::int AS published_total
        FROM latest
        """
    )
    content_performance = await _rows(
        pool,
        """
        WITH latest AS (
          SELECT DISTINCT ON (pm.schedule_id)
                 pm.schedule_id, pm.views, pm.likes, pm.comments, pm.impressions,
                 pm.avg_watch_s, pm.ctr, pm.avg_view_duration_s, pm.retention_3s,
                 pm.retention_3s_estimated, pm.link_clicks, pm.subscribers_gained,
                 pm.captured_at, pm.source, pm.report_start, pm.report_end,
                 pm.metric_definition, pm.degraded, pm.degradation_detail
          FROM post_metrics pm
          ORDER BY pm.schedule_id, pm.captured_at DESC
        )
        SELECT s.id, s.platform, s.language, o.title AS offer_title, s.remote_post_id,
               l.views, l.likes, l.comments, l.impressions, l.avg_watch_s,
               l.ctr, l.avg_view_duration_s, l.retention_3s,
               l.retention_3s_estimated, l.link_clicks,
               l.subscribers_gained, l.captured_at, l.source,
               l.report_start, l.report_end, l.metric_definition,
               l.degraded, l.degradation_detail,
               s.description_patched_at
        FROM schedules s
        JOIN offers o ON o.id = s.offer_id
        JOIN latest l ON l.schedule_id = s.id
        WHERE s.state = 'published'
        ORDER BY l.views DESC NULLS LAST, l.captured_at DESC
        LIMIT 25
        """
    )

    # ---- v0.27 closed-loop growth briefing. Read-only and conservative:
    # recommendations say "test", never "this caused the result".
    growth_rows = await _rows(
        pool,
        """
        WITH latest AS (
          SELECT DISTINCT ON (pm.schedule_id)
                 pm.schedule_id, pm.views, pm.likes, pm.comments, pm.impressions,
                 pm.avg_watch_s, pm.ctr, pm.avg_view_duration_s,
                 pm.avg_view_percentage, pm.retention_3s, pm.retention_3s_estimated,
                 pm.link_clicks, pm.subscribers_gained, pm.captured_at
          FROM post_metrics pm
          ORDER BY pm.schedule_id, pm.captured_at DESC
        )
        SELECT s.id AS schedule_id, s.platform, s.language, s.metadata_variant,
               o.title AS offer_title, l.views, l.likes, l.comments, l.impressions,
               l.avg_watch_s, l.ctr, l.avg_view_duration_s,
               l.avg_view_percentage, l.retention_3s, l.retention_3s_estimated,
               l.link_clicks, l.subscribers_gained, l.captured_at
        FROM schedules s
        JOIN offers o ON o.id = s.offer_id
        JOIN latest l ON l.schedule_id = s.id
        WHERE s.state = 'published'
        ORDER BY l.captured_at DESC
        LIMIT 200
        """
    )
    language_performance = await _rows(
        pool,
        """
        WITH latest AS (
          SELECT DISTINCT ON (pm.schedule_id)
                 pm.schedule_id, pm.views, pm.likes, pm.comments
          FROM post_metrics pm
          ORDER BY pm.schedule_id, pm.captured_at DESC
        )
        SELECT s.language, COUNT(*)::int AS posts,
               SUM(l.views)::bigint AS views,
               AVG(l.views)::double precision AS avg_views,
               SUM(l.likes + l.comments)::bigint AS interactions
        FROM schedules s
        JOIN latest l ON l.schedule_id = s.id
        WHERE s.state = 'published'
        GROUP BY s.language
        ORDER BY avg_views DESC
        """
    )
    experiments = await _rows(
        pool,
        """
        SELECT id, offer_id, schedule_id, variant_id, language, platform,
               hypothesis, metric, status, result::text AS result,
               created_at, updated_at
        FROM content_experiments
        ORDER BY created_at DESC LIMIT 50
        """
    )
    stale_topics_raw = await pool.fetchval(
        """
        SELECT COUNT(*) FROM trend_candidates
        WHERE status = 'radar' AND updated_at < now() - interval '7 days'
        """
    )
    try:
        stale_topics = int(stale_topics_raw or 0)
    except (TypeError, ValueError):
        stale_topics = 0  # fake/legacy pool returned a non-count value
    growth = growth_summarize(
        growth_rows,
        languages=language_performance,
        experiments=experiments,
        stale_topics=stale_topics,
    )
    trend_summary = await pool.fetchrow(
        """
        SELECT COUNT(*)::int AS total,
               COUNT(*) FILTER (WHERE score >= 78)::int AS hot,
               COUNT(*) FILTER (WHERE status = 'shortlisted')::int AS shortlisted,
               COALESCE(AVG(score), 0)::double precision AS average_score
        FROM trend_candidates
        """
    )

    generated_at = await pool.fetchval("SELECT now()")

    # Cost per published video (WP-F §5.5): spend over output — the one
    # money number a productivity decision actually needs.
    from costs_store import spend_summary as _cost_summary
    costs = await _cost_summary(pool)

    body = {
        "items_total": funnel[0]["n"] if funnel else 0,
        "offers_by_state": offers_by_state,
        "verification": dict(verification or {}),
        "schedules_by_state": schedules_by_state,
        "schedules_by_platform": schedules_by_platform,
        "publishing": dict(publishing or {}),
        "rendering": dict(rendering or {}),
        "source_freshness": source_freshness,
        "account_health": account_health,
        "metrics_totals": dict(metrics_totals or {}),
        "content_performance": content_performance,
        "growth": growth,
        "language_performance": language_performance,
        "experiments": experiments,
        "trend_summary": dict(trend_summary or {}),
        "cost_usd_30d": costs["usd_30d"],
        "cost_per_published_video_usd_30d":
            costs["cost_per_published_video_usd_30d"],
        "generated_at": generated_at,
        "cached": False,
    }
    await cache_set_json(ANALYTICS_KEY, body)
    return body
