-- Weeks 3-4: Verification desk (master plan §3, §18)
-- "Every verified field links to evidence; unverified records cannot enter
--  script generation."

-- Structured LLM/manual extraction results, each field mapped to evidence.
CREATE TABLE extractions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id    UUID NOT NULL REFERENCES offers(id),
  fields      JSONB NOT NULL DEFAULT '{}',  -- field → {value, evidence_url, excerpt, confidence}
  conflicts   JSONB NOT NULL DEFAULT '[]',  -- disagreeing fields across sources
  complete    BOOLEAN NOT NULL DEFAULT FALSE,
  model       TEXT,                          -- 'rules/0.1' or the LLM id used
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_extractions_offer ON extractions(offer_id, created_at DESC);

-- Evidence integrity flags: verified requires official + provider-domain-checked sources.
ALTER TABLE evidence ADD COLUMN official BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE evidence ADD COLUMN domain_ok BOOLEAN NOT NULL DEFAULT FALSE;

-- Immutable evidence: same offer + same content hash must never duplicate.
CREATE UNIQUE INDEX uq_evidence_offer_hash ON evidence(offer_id, content_hash);
