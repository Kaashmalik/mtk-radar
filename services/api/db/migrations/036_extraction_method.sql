-- WP-G (enhancement plan 2026-10-24 §5.6.3): honest extraction attribution.
--
-- `method` records HOW a proposal was produced: 'llm' (the model produced or
-- confirmed the fields), 'rules' (deterministic extractor only — no LLM
-- configured/attempted) or 'rules_fallback' (the LLM WAS attempted but
-- produced nothing usable — timeout, budget, bad payload). Nullable: rows
-- written before this column exist carry no claim, and the API never invents
-- one. The operator must be able to see when verification silently ran on
-- the deterministic path — a degraded LLM day must never look like a normal
-- one.
ALTER TABLE extractions ADD COLUMN IF NOT EXISTS method TEXT;

ALTER TABLE extractions ADD CONSTRAINT extractions_method_known
  CHECK (method IS NULL OR method IN ('llm', 'rules', 'rules_fallback'));
