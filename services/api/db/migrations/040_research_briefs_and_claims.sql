-- EP-03 G18 + research briefs: content-type tracks and a versioned claim
-- ledger.
--
-- Promotion used to force EVERY topic into an offer-shaped container
-- (offer_type='trend_topic') whose extraction/script templates then rendered
-- coupon/eligibility sections around fields that do not exist for research
-- content. Three production tracks are explicit instead:
--   explainer         official/research explainer — attributed claims only,
--                     automated safe assets allowed, never claims testing
--   tested_tutorial   needs a human-redaction-reviewed capture
--   claim_walkthrough needs a reviewer-attested demonstrated claim
--   offer             real discount/offer content — the offer-specific
--                     eligibility/renewal gates stay EXACTLY where they were
--
-- research_briefs are VERSIONED rows (a new version supersedes, never
-- rewrites); research_claims are the claim ledger: class-tagged
-- (author_reported / independently_reproduced / tested_by_mtk /
-- editorial_analysis — a preprint is not peer review; "the authors report X"
-- is sourcing, "X is the best" is not a claim), scope-bound, with
-- contradicted/unknown state and a recheck policy.

CREATE TABLE IF NOT EXISTS research_briefs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id        UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
  version         INTEGER NOT NULL DEFAULT 1,
  content_type    TEXT NOT NULL CHECK (content_type IN
                    ('explainer', 'tested_tutorial', 'claim_walkthrough', 'offer')),
  viewer_question TEXT,
  angle           TEXT,
  audience        TEXT,
  sources         JSONB NOT NULL DEFAULT '[]',        -- [{url, owner, date, note}]
  counterevidence JSONB NOT NULL DEFAULT '[]',        -- contradictory findings
  limitations     TEXT,
  auto_shortlisted BOOLEAN NOT NULL DEFAULT FALSE,    -- low-risk auto-shortlist flag
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (offer_id, version)
);

CREATE INDEX IF NOT EXISTS idx_research_briefs_offer
  ON research_briefs (offer_id, version DESC);

CREATE TABLE IF NOT EXISTS research_claims (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brief_id          UUID NOT NULL REFERENCES research_briefs(id) ON DELETE CASCADE,
  offer_id          UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
  claim_text        TEXT NOT NULL,                    -- the substantive sentence
  claim_class       TEXT NOT NULL CHECK (claim_class IN
                      ('author_reported', 'independently_reproduced',
                       'tested_by_mtk', 'editorial_analysis')),
  supporting_excerpt TEXT,
  source_url        TEXT,
  source_owner      TEXT,
  source_date       DATE,
  scope             TEXT,                             -- hardware/dataset/version/region
  status            TEXT NOT NULL DEFAULT 'unknown' CHECK (status IN
                      ('supported', 'contradicted', 'unknown')),
  permitted_wording TEXT,                             -- exact wording the script may use
  recheck_at        TIMESTAMPTZ,
  status_changed_by TEXT,
  status_changed_at TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_research_claims_brief
  ON research_claims (brief_id, status);

-- The production queue carries the track so capture/render requirements are
-- computable from the row itself.
ALTER TABLE production_queue
  ADD COLUMN IF NOT EXISTS content_type TEXT
    CHECK (content_type IN ('explainer', 'tested_tutorial', 'claim_walkthrough', 'offer'));
