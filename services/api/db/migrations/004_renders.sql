-- Weeks 7-8: Video pipeline (master plan §5, §18)
-- "A full video project can be regenerated from versioned source assets."

CREATE TABLE renders (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id       UUID NOT NULL REFERENCES offers(id),
  capture_id     UUID REFERENCES capture_sessions(id),
  script_version INTEGER,
  preset         TEXT NOT NULL,               -- 'landscape' (16:9) | 'vertical' (9:16)
  width          INTEGER NOT NULL,
  height         INTEGER NOT NULL,
  duration_s     NUMERIC(8,2),
  video_path     TEXT NOT NULL,
  captions_path  TEXT,
  disclosure     JSONB NOT NULL DEFAULT '{}', -- synthetic narration/visuals labels (§5)
  status         TEXT NOT NULL DEFAULT 'rendered',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_renders_offer ON renders(offer_id, created_at DESC);
