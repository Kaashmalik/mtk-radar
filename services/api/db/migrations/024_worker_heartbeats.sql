-- v0.30: worker liveness for the laptop-first operator console.
--
-- A pipeline can look healthy while a worker is dead: the API answers, the
-- queue is readable, and nothing publishes. Each long-running worker posts a
-- heartbeat on its own cadence; the dashboard and monitor treat a missing or
-- stale heartbeat as an alert (never as a successful quiet period).
--
-- Metadata is operational only (for example the monitor's notification
-- channel summary or the render worker's FFmpeg path). It must never contain a
-- credential, token, or captured content.

CREATE TABLE IF NOT EXISTS worker_heartbeats (
  worker        TEXT PRIMARY KEY,
  status        TEXT NOT NULL DEFAULT 'ok'
                CHECK (status IN ('starting', 'ok', 'degraded', 'stopped', 'error')),
  detail        TEXT,
  metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
  interval_s    INTEGER NOT NULL DEFAULT 60
                CHECK (interval_s BETWEEN 5 AND 86400),
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_seen
  ON worker_heartbeats (last_seen_at DESC);
