-- v0.34: Trend Radar v2 (WP-B, enhancement plan 2026-10-24) —
-- per-candidate velocity time-series and corroboration counts.
--
-- The v1 radar scored each inbox item exactly once and decayed by age: a
-- topic that was "trending" (rising fast on many sources) was invisible.
-- This migration gives every candidate a score history so velocity is real
-- math, and records how many independent sources observed the same story.
--
-- Nothing here changes the safety model: trend rows stay proposals; the
-- trend_scan job below is the recurring arm that keeps the radar alive.

ALTER TABLE trend_candidates
  ADD COLUMN IF NOT EXISTS velocity REAL NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS peak_score REAL NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS corroboration INTEGER NOT NULL DEFAULT 0;

-- One row per re-score. The EMA velocity (trend_engine.smooth_velocity) reads
-- the previous observation; the dashboard sparkline reads the last N.
CREATE TABLE IF NOT EXISTS trend_observations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID NOT NULL REFERENCES trend_candidates(id) ON DELETE CASCADE,
  score        NUMERIC(5,2) NOT NULL,
  velocity     REAL NOT NULL DEFAULT 0,
  sources      INTEGER NOT NULL DEFAULT 0,
  observed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trend_observations_candidate
  ON trend_observations (candidate_id, observed_at DESC);

-- Recurring radar scan (collector-style: re-armed by a healthy scan inside
-- trends_api.py, retried with the same budget on failure, dead-lettered into
-- operator attention after 5 consecutive failures).
INSERT INTO jobs (kind, dedupe_key, run_after, max_attempts)
SELECT 'trend_scan', 'trend_scan', now(), 5
WHERE NOT EXISTS (SELECT 1 FROM jobs WHERE dedupe_key = 'trend_scan');
