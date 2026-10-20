-- Week 9: Editing handoff, calendar, approval/version controls (master plan §17, §18)
-- "A creator can make edits and schedule a test post with rollback/pause."

-- Exact-version approval: schedule may only go live against the approved hash;
-- material edits generate a new hash → reapproval required (§17).
ALTER TABLE schedules ADD COLUMN version_hash TEXT;
ALTER TABLE schedules ADD COLUMN approved_by TEXT;
ALTER TABLE schedules ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}';   -- platform-specific copy
ALTER TABLE schedules ADD COLUMN offer_evidence_ok BOOLEAN NOT NULL DEFAULT FALSE;  -- evidence snapshot revalidated at scheduling time
