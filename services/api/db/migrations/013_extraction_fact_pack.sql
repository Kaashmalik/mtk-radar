-- WP01 slice 2: the server derives a fact pack for every claim field
-- (supported / contradicted / unknown / not_applicable) and checks it against
-- the offer-type terms contract (master plan §6 steps 5-9).
--
-- The pack is stored so a reviewer can see WHY a proposal was accepted or
-- blocked, instead of a bare boolean. It is derived output: the promotion
-- gate re-derives it and never trusts the stored value.
ALTER TABLE extractions ADD COLUMN fact_pack JSONB NOT NULL DEFAULT '{}';

-- The offer type the pack was derived against, kept for the record only. The
-- gate re-derives against the CURRENT offer type, so re-typing an offer
-- invalidates the old pack instead of letting it be inherited.
ALTER TABLE extractions ADD COLUMN offer_type TEXT NOT NULL DEFAULT '';

-- A stored pack must be a JSON object, never a scalar or list.
ALTER TABLE extractions ADD CONSTRAINT extraction_fact_pack_is_object
    CHECK (jsonb_typeof(fact_pack) = 'object');
