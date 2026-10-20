-- Week 11: expiry monitor + corrections (master plan §17/§18)
-- Exit criterion: "Posts pause when an offer expires; corrections link to
-- affected videos."

-- Correction log: what changed, who corrected, which script version it refers to.
CREATE TABLE offer_corrections (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id     UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
  note         TEXT NOT NULL,
  corrected_by TEXT NOT NULL,
  version_hash TEXT,                    -- script version the correction supersedes, if any
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_corrections_offer ON offer_corrections(offer_id, created_at DESC);

-- §17: "automatically pause affected posts if the offer expires or changes."
-- Enforced at the DATABASE level so /transition, /sweep-stale, or any future
-- writer cannot leave scheduled posts dangling on a dead offer. Scheduled
-- posts may only exist while the offer is in a video-allowed state.
CREATE OR REPLACE FUNCTION pause_posts_on_offer_change() RETURNS trigger AS $$
BEGIN
  IF NEW.state::text IN ('verified', 'approved_for_video', 'published') THEN
    RETURN NEW;  -- still claimable; scheduled posts may stand
  END IF;

  UPDATE schedules
  SET state = 'paused',
      outcome_detail = jsonb_build_object(
        'detail', 'auto-paused: offer state -> ' || NEW.state::text,
        'auto_paused', true, 'offer_state', NEW.state::text
      ),
      updated_at = now()
  WHERE offer_id = NEW.id
    AND state = 'scheduled';

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pause_on_offer_change
AFTER UPDATE OF state ON offers
FOR EACH ROW
WHEN (OLD.state::text IS DISTINCT FROM NEW.state::text)
EXECUTE FUNCTION pause_posts_on_offer_change();
