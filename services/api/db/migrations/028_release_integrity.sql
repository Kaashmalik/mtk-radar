-- v0.32: release integrity and durable job infrastructure.
--
-- Three things were structural gaps in the 22 Oct audit:
--   1. A human playback review of the FINAL export had no schema to live in,
--      so "it played correctly" could never be recorded or gated on.
--   2. Render registration was not idempotent: a retry after a lost response
--      (or two workers on one candidate) double-registered.
--   3. Orchestration was row-state only: nothing durable recorded "this work
--      is owed", so a restart silently lost in-flight intent.

-- 1) Playback / timeline review of the final export (§6.F: final human
--    playback-review gate). Set by a human-only API endpoint; the release
--    gate refuses schedules whose pinned render was never signed off.
ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS playback_approved BOOLEAN,
  ADD COLUMN IF NOT EXISTS playback_reviewer TEXT,
  ADD COLUMN IF NOT EXISTS playback_note TEXT,
  ADD COLUMN IF NOT EXISTS playback_reviewed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS timeline JSONB;

COMMENT ON COLUMN renders.playback_approved IS
  'True when a named human signed off the final export playback.';
COMMENT ON COLUMN renders.timeline IS
  'Speech-authoritative scene timeline used for the export (QC trail).';

-- 2) Idempotent render registration: the same output for the same script
--    revision is the same render, no matter which worker registered it or
--    how many times a retry replayed the request.
CREATE UNIQUE INDEX IF NOT EXISTS renders_revision_output_key
  ON renders (offer_id, language, preset, script_version_hash, video_sha256)
  WHERE video_sha256 IS NOT NULL AND script_version_hash IS NOT NULL;

-- 3) Durable job/outbox table (§8.A). Workers still poll their lists today,
--    but "owed work" is now recorded durably with claim/lease semantics so a
--    restart can see exactly what was in flight, and a wedged job becomes
--    visible instead of silent.
CREATE TABLE jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind TEXT NOT NULL,
  entity_id UUID,
  payload JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'leased', 'done', 'failed', 'dead', 'cancelled')),
  run_after TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_expires_at TIMESTAMPTZ,
  lease_holder TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 5,
  last_error TEXT,
  dedupe_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_pending_due
  ON jobs (run_after) WHERE status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS jobs_wedged
  ON jobs (lease_expires_at) WHERE status = 'leased';

-- 4) A schedule can now be explicitly cancelled (human decision), instead of
--    being mislabelled 'failed' to get it out of the queue.
ALTER TYPE schedule_state ADD VALUE IF NOT EXISTS 'cancelled' AFTER 'paused';
