-- v0.29: measured render QC gate.
--
-- A render row now records the deterministic QC report that was measured from
-- the exact output bytes. Existing/legacy rows default to not_checked and are
-- deliberately blocked by scheduling and publishing until re-rendered.
--
-- status: rendered | qc_failed | render_failed
-- qc_status: passed | failed | not_checked (legacy rows only)
--
-- Failed attempts remain in this table as the dead-letter record; candidate
-- selection ignores them so an offer stays retryable.

ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS qc_status TEXT NOT NULL DEFAULT 'not_checked';
ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS qc_report JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS qc_checked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_renders_qc
  ON renders (qc_status, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_renders_dead_letter
  ON renders (status, created_at DESC);
