-- Weeks 5-6: Script & checklist + capture workflow (master plan §4, §18)
-- "One eligible claim can be recorded and reviewed without leaking secrets."

-- Versioned generated scripts: never overwrite; reviewers approve exact versions.
CREATE TABLE offer_scripts (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id      UUID NOT NULL REFERENCES offers(id),
  version       INTEGER NOT NULL,
  markdown      TEXT NOT NULL,
  checklist     JSONB NOT NULL DEFAULT '[]',
  command_cards JSONB NOT NULL DEFAULT '[]',
  created_by    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (offer_id, version)
);

-- Guided capture sessions: real-browser recording of a genuinely eligible claim.
CREATE TABLE capture_sessions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id           UUID NOT NULL REFERENCES offers(id),
  video_path         TEXT,                          -- object storage key (asset itself is NOT stored here)
  step_log           JSONB NOT NULL DEFAULT '[]',   -- navigated pages + timestamps
  secret_findings    JSONB NOT NULL DEFAULT '[]',   -- pattern names + counts ONLY, never secret values
  redaction_reviewed BOOLEAN NOT NULL DEFAULT FALSE,
  reviewer           TEXT,
  review_note        TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_scripts_offer ON offer_scripts(offer_id, version DESC);
CREATE INDEX idx_captures_offer ON capture_sessions(offer_id);
