-- v0.36: Hashtag performance rollup (WP-E, enhancement plan 2026-10-24).
--
-- The feedback loop for the packaging engine: every daily metrics snapshot is
-- rolled up per (platform, tag) so generation can stop proposing tags that
-- consistently underperform. The rollup is derived data — recomputable from
-- schedules.metadata ⋈ post_metrics — and here it is maintained at snapshot
-- ingest (services/api/schedules_api.py:ingest_metrics).
CREATE TABLE IF NOT EXISTS hashtag_performance (
  platform          TEXT NOT NULL,
  tag               TEXT NOT NULL,      -- with '#', as proposed by the engine
  posts             INTEGER NOT NULL DEFAULT 0,
  impressions_total BIGINT NOT NULL DEFAULT 0,
  views_total       BIGINT NOT NULL DEFAULT 0,
  last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (platform, tag)
);

CREATE INDEX IF NOT EXISTS idx_hashtag_performance_seen
  ON hashtag_performance (platform, last_seen_at DESC);
