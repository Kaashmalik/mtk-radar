-- v0.26: automation policy visibility (master plan §17 automation/human gates)
--
-- The policy itself lives in settings (key = 'automation_policy'); these
-- indexes keep the operator status read and the daily auto-publish budget
-- cheap as the audit trail grows.

CREATE INDEX IF NOT EXISTS idx_audit_actor_time
  ON audit_log (actor, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_schedules_approved_by
  ON schedules (approved_by, updated_at DESC)
  WHERE approved_by IS NOT NULL;
