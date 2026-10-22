-- v0.31: format-specific scripts + human claim-outcome attestation.
--
-- A script may only say "I claimed this and it worked" when a reviewer has
-- watched the capture and explicitly recorded that the benefit was demonstrated.
-- Merely having footage is not proof of a successful claim.
--
-- Formats:
--   official_explainer  — explain the official terms; no first-person claim
--   tested_tutorial     — show tested setup steps; result wording follows the
--                         attested outcome (never a staged success)
--   claim_walkthrough   — first-person claim; requires demonstrated outcome

ALTER TABLE capture_sessions
  ADD COLUMN IF NOT EXISTS claim_outcome TEXT;
ALTER TABLE capture_sessions
  ADD COLUMN IF NOT EXISTS claim_outcome_reviewer TEXT;
ALTER TABLE capture_sessions
  ADD COLUMN IF NOT EXISTS claim_outcome_at TIMESTAMPTZ;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'capture_sessions_claim_outcome_check'
  ) THEN
    ALTER TABLE capture_sessions
      ADD CONSTRAINT capture_sessions_claim_outcome_check
      CHECK (
        claim_outcome IS NULL
        OR claim_outcome IN ('demonstrated', 'not_demonstrated', 'not_attempted')
      );
  END IF;
END $$;

ALTER TABLE offer_scripts
  ADD COLUMN IF NOT EXISTS format TEXT NOT NULL DEFAULT 'official_explainer';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'offer_scripts_format_check'
  ) THEN
    ALTER TABLE offer_scripts
      ADD CONSTRAINT offer_scripts_format_check
      CHECK (format IN ('official_explainer', 'tested_tutorial', 'claim_walkthrough'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_captures_offer_format
  ON capture_sessions (offer_id, claim_outcome);
