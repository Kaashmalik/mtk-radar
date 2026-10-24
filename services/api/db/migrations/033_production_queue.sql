-- v0.35: Production Queue (WP-C, enhancement plan 2026-10-24) — the ranked
-- "videos to make" list that replaces two unrelated lists (radar dead-ends
-- and the unscored render queue).
--
-- Rows are created from PROMOTED trend topics (POST /trends/{id}/promote —
-- offer + queue row in one transaction) and from verified offers awaiting
-- capture. The rank is NOT stored: it is recomputed on read from stored,
-- recomputable components (see docs/production-queue.md and queue_api.py) —
-- a stored rank always drifts from the live evidence it ranks.
--
-- Safety model unchanged: a queue row is a proposal. Verification, capture,
-- redaction review and publish approval stay exactly where they were.

CREATE TABLE IF NOT EXISTS production_queue (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id          UUID UNIQUE REFERENCES offers(id) ON DELETE SET NULL,
  trend_id          UUID REFERENCES trend_candidates(id) ON DELETE SET NULL,
  title             TEXT NOT NULL,
  provider          TEXT,
  category          TEXT,
  kind              TEXT NOT NULL DEFAULT 'timely'
                    CHECK (kind IN ('timely', 'evergreen')),
  preset_fit        SMALLINT CHECK (preset_fit IS NULL OR
                                    (preset_fit >= 0 AND preset_fit <= 100)),
  trend_snapshot    JSONB NOT NULL DEFAULT '{}',
  expires_at        TIMESTAMPTZ,
  rank_pinned       INTEGER,          -- operator override (POST /queue/reorder)
  status            TEXT NOT NULL DEFAULT 'ready'
                    CHECK (status IN ('ready', 'archived')),
  archived_reason   TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Default morning-read ordering: pinned rows first, then rank.
CREATE INDEX IF NOT EXISTS idx_production_queue_status
  ON production_queue (status, rank_pinned NULLS LAST, created_at DESC);

-- The trend side already records 'promoted' in status via PATCH; this
-- constraint documents the lifecycle (radar → shortlisted → promoted).
-- No DDL needed — TrendStatusIn already validates the enum.
