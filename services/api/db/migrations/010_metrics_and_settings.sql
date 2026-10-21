-- v0.18: audience analytics ingestion + scheduling settings (master plan §7/§17/§11)

-- Per-post audience metrics snapshots, pulled from platform APIs by the
-- metrics worker. raw keeps the provider payload verbatim for re-parsing;
-- normalized columns feed the analytics aggregates.
CREATE TABLE post_metrics (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  schedule_id  UUID NOT NULL REFERENCES schedules(id),
  platform     TEXT NOT NULL,
  captured_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  views        BIGINT,
  likes        BIGINT,
  comments     BIGINT,
  impressions  BIGINT,
  avg_watch_s  NUMERIC(12,2),
  source       TEXT NOT NULL,               -- youtube-analytics | graph-insights
  raw          JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_post_metrics_schedule ON post_metrics (schedule_id, captured_at DESC);

-- §17: "configure publish windows in settings" — a tiny KV for operator
-- preferences (value JSONB; e.g. {"windows": ["18:00", "20:30"]}).
CREATE TABLE settings (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  updated_by TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §11 close-out: marker for the worker that pushes correction notices into
-- already-published descriptions (idempotent — no double-patching).
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS description_patched_at TIMESTAMPTZ;
