-- v0.16: publish-time approval integrity + reviewer identity (master plan §11/§17)

-- §17: "Approved — a reviewer approved this exact version hash." Renders now
-- carry the hash of the exact script markdown they were produced from, so the
-- publishing worker can verify render ← → approval binding at upload time.
-- NULL (legacy rows) fails closed: re-render to bind the approval hash.
ALTER TABLE renders ADD COLUMN IF NOT EXISTS script_version_hash TEXT;

-- Reviewer identity: personal API tokens. Only sha256(token) is stored —
-- plaintext tokens are shown once at mint time (same pattern as GitHub PATs).
-- The shared MTK_API_TOKEN keeps working for workers/extension (no identity);
-- a reviewer token binds audit_log.actor and reviewer fields to the token
-- owner, and keeps the master token out of browsers.
CREATE TABLE reviewers (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL UNIQUE,
  token_hash  TEXT NOT NULL UNIQUE,
  active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_entity ON audit_log (entity, entity_id);
