-- Schema fix: `schedules` was created in 001 without an `offer_id` column, but
-- every schedule path links a schedule back to its offer:
--   - services/api/schedules_api.py  (INSERT ... offer_id, calendar JOIN, approve)
--   - migration 007's pause_posts_on_offer_change() trigger (WHERE offer_id = NEW.id)
-- Without the column, schedule creation, the calendar listing, and the
-- auto-pause-on-expiry trigger all fail at runtime.
ALTER TABLE schedules ADD COLUMN IF NOT EXISTS offer_id UUID REFERENCES offers(id) ON DELETE CASCADE;

-- Backfill any schedule that predates this column via the week-1 projects table.
UPDATE schedules s
SET offer_id = p.offer_id
FROM projects p
WHERE p.id = s.project_id AND s.offer_id IS NULL;

-- The week-9 API links a schedule to an offer + render + script version and
-- never populates project_id, so that NOT NULL FK has to become optional.
ALTER TABLE schedules ALTER COLUMN project_id DROP NOT NULL;

-- Every schedule created by the API carries an offer_id; enforce it once no
-- orphaned rows remain (older deployments may still have stragglers).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM schedules WHERE offer_id IS NULL) THEN
    ALTER TABLE schedules ALTER COLUMN offer_id SET NOT NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_schedules_offer ON schedules(offer_id, local_time);
