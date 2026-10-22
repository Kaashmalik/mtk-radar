-- v0.31: persisted resumable-upload sessions.
--
-- A YouTube resumable session URI is a short-lived bearer capability: anyone
-- holding it can finish that upload. It is therefore never returned to the
-- dashboard, only to service/worker credentials, and rows expire quickly.
-- At-rest protection comes from database access control + storage encryption;
-- the API never logs or lists the URI.
--
-- Progress is the last offset the provider confirmed, not the bytes the worker
-- attempted. A crashed worker therefore resumes from observable progress (or
-- asks the provider for the actual offset) instead of guessing.

CREATE TABLE IF NOT EXISTS upload_sessions (
  schedule_id    UUID PRIMARY KEY REFERENCES schedules(id) ON DELETE CASCADE,
  provider       TEXT NOT NULL CHECK (provider IN ('youtube')),
  session_uri    TEXT NOT NULL CHECK (length(session_uri) BETWEEN 20 AND 4096),
  content_length BIGINT NOT NULL CHECK (content_length >= 0),
  bytes_sent     BIGINT NOT NULL DEFAULT 0
                 CHECK (bytes_sent >= 0 AND bytes_sent <= content_length),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_upload_sessions_expiry
  ON upload_sessions (expires_at);
