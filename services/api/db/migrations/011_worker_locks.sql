-- v0.22: worker locks — one active publisher/metrics sweep per deployment.
--
-- A deploy overlap (old container still draining, new container already up)
-- or an operator running a second worker by hand would otherwise upload the
-- same post twice. The lock is a row with an expiry: if a worker dies, the
-- lock ages out and the next sweep takes over.
CREATE TABLE worker_locks (
  name        TEXT PRIMARY KEY,
  holder      TEXT,
  acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_worker_locks_expiry ON worker_locks (expires_at);
