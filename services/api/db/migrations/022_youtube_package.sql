-- v0.28: YouTube-first immutable publishing package + remote confirmation.
--
-- A schedule used to pin only the approved script hash. The publisher then
-- re-selected the "latest" render at upload time, so a new render could
-- silently replace the file a reviewer approved. These columns pin the exact
-- render bytes, metadata, cover and captions at scheduling time.
--
-- We also record what the remote platform actually confirmed. A post is only
-- `published` after the worker has verified processing + visibility (for
-- YouTube: videos.list status/processingDetails). `remote_metadata` keeps the
-- per-operation results (thumbnail, captions, playlist, comment) without ever
-- storing credentials.

ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS video_sha256 TEXT;
ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS captions_sha256 TEXT;
ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS cover_sha256 TEXT;

ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS render_id UUID REFERENCES renders(id) ON DELETE SET NULL;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS platform_account_id UUID REFERENCES platform_accounts(id) ON DELETE SET NULL;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS package_hash TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS render_sha256 TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS metadata_hash TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS cover_sha256 TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS captions_sha256 TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS remote_url TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS remote_processing_state TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS remote_privacy TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS published_confirmed_at TIMESTAMPTZ;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS remote_metadata JSONB NOT NULL DEFAULT '{}';
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS youtube_playlist_id TEXT;

CREATE INDEX IF NOT EXISTS idx_schedules_due
  ON schedules (state, local_time) WHERE state = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_schedules_render
  ON schedules (render_id);

-- YouTube Analytics gives impressions/CTR/AVD/percentage/subscribers; the
-- parser stores the raw report too, so a later re-parse never loses data.
ALTER TABLE post_metrics
  ADD COLUMN IF NOT EXISTS shares BIGINT;
ALTER TABLE post_metrics
  ADD COLUMN IF NOT EXISTS avg_view_percentage NUMERIC(8,4);

-- Experiment decisions are evidence, not just a status flip.
ALTER TABLE content_experiments
  ADD COLUMN IF NOT EXISTS decision_note TEXT;
ALTER TABLE content_experiments
  ADD COLUMN IF NOT EXISTS decided_by TEXT;
ALTER TABLE content_experiments
  ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ;
