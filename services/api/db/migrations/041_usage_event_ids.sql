-- 2026-10-28 plan (EP-07): idempotent usage telemetry.
--
-- Workers now spool failed usage reports to a durable outbox and replay
-- them. A report whose HTTP response was lost may already be recorded, so
-- every event carries a client-generated `event_id`; a replay with a known
-- id is a no-op. NULL stays allowed for older workers (no dedup, as before).
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS event_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_events_event_id
  ON usage_events (event_id) WHERE event_id IS NOT NULL;
