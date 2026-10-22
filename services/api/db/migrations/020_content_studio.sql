-- v0.27: content studio, trend radar, bilingual variants, growth loop.
--
-- The v0.26 pipeline proves an offer and publishes a truthful walkthrough.
-- This migration adds the *content layer* around that truth layer:
--   * trend_candidates      — scored discovery leads (radar)
--   * content_variants      — language/platform variants of a script, metadata,
--                             cover spec, narration or captions
--   * experiment tracking   — measured packaging choices (hook/title/cover)
--   * language/cover fields — carried through script -> render -> schedule
--
-- Nothing here weakens the approval contract: a schedule still pins the exact
-- script hash, and content variants are additive reviewable assets.

-- ---------------------------------------------------------------- scripts
ALTER TABLE offer_scripts
  ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en';
ALTER TABLE offer_scripts
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';

-- Scripts are now versioned per language. The old unique(offer_id, version)
-- would collide when English v1 and Urdu v1 are generated together.
ALTER TABLE offer_scripts
  DROP CONSTRAINT IF EXISTS offer_scripts_offer_id_version_key;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'offer_scripts_offer_language_version_key'
  ) THEN
    ALTER TABLE offer_scripts
      ADD CONSTRAINT offer_scripts_offer_language_version_key
      UNIQUE (offer_id, language, version);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_scripts_offer_language
  ON offer_scripts (offer_id, language, version DESC);

-- ---------------------------------------------------------------- renders
ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en';
ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS cover_path TEXT;
ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS motion_template TEXT NOT NULL DEFAULT 'studio';
ALTER TABLE renders
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_renders_offer_language
  ON renders (offer_id, language, created_at DESC);

-- ------------------------------------------------------------- schedules
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en';
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS content_variant_id UUID;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS cover_path TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS pinned_comment TEXT;
ALTER TABLE schedules
  ADD COLUMN IF NOT EXISTS metadata_variant TEXT NOT NULL DEFAULT 'default';

CREATE INDEX IF NOT EXISTS idx_schedules_language
  ON schedules (language, platform, state);

-- --------------------------------------------------------------- metrics
ALTER TABLE post_metrics
  ADD COLUMN IF NOT EXISTS ctr NUMERIC(8,4);
ALTER TABLE post_metrics
  ADD COLUMN IF NOT EXISTS avg_view_duration_s NUMERIC(12,2);
ALTER TABLE post_metrics
  ADD COLUMN IF NOT EXISTS retention_3s NUMERIC(8,4);
ALTER TABLE post_metrics
  ADD COLUMN IF NOT EXISTS link_clicks INTEGER;
ALTER TABLE post_metrics
  ADD COLUMN IF NOT EXISTS subscribers_gained INTEGER;

-- ------------------------------------------------------- trend candidates
CREATE TABLE IF NOT EXISTS trend_candidates (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id           UUID REFERENCES items(id) ON DELETE SET NULL,
  title             TEXT NOT NULL,
  url               TEXT NOT NULL,
  source_provider   TEXT,
  source_category   TEXT,
  country_scope     TEXT[] NOT NULL DEFAULT '{}',
  language          TEXT NOT NULL DEFAULT 'en',
  demand_score      NUMERIC(5,2) NOT NULL DEFAULT 0,
  freshness_score   NUMERIC(5,2) NOT NULL DEFAULT 0,
  feasibility_score NUMERIC(5,2) NOT NULL DEFAULT 0,
  competition_gap   NUMERIC(5,2) NOT NULL DEFAULT 0,
  audience_fit      NUMERIC(5,2) NOT NULL DEFAULT 0,
  monetization      NUMERIC(5,2) NOT NULL DEFAULT 0,
  score             NUMERIC(5,2) NOT NULL DEFAULT 0,
  score_reason      JSONB NOT NULL DEFAULT '{}',
  signals           JSONB NOT NULL DEFAULT '{}',
  status            TEXT NOT NULL DEFAULT 'radar',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT trend_status_check
    CHECK (status IN ('radar', 'shortlisted', 'promoted', 'dismissed')),
  CONSTRAINT trend_score_check
    CHECK (score >= 0 AND score <= 100)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_trend_candidates_url
  ON trend_candidates (url);
CREATE INDEX IF NOT EXISTS idx_trend_candidates_score
  ON trend_candidates (status, score DESC, updated_at DESC);

-- ------------------------------------------------------- content variants
CREATE TABLE IF NOT EXISTS content_variants (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id      UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
  language      TEXT NOT NULL DEFAULT 'en',
  kind          TEXT NOT NULL,
  platform      TEXT,
  variant_key   TEXT NOT NULL DEFAULT 'default',
  payload       JSONB NOT NULL DEFAULT '{}',
  text_content  TEXT,
  status        TEXT NOT NULL DEFAULT 'draft',
  version       INTEGER NOT NULL DEFAULT 1,
  version_hash  TEXT,
  created_by    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT content_variant_kind_check
    CHECK (kind IN ('script', 'metadata', 'cover', 'narration', 'captions', 'hook')),
  CONSTRAINT content_variant_status_check
    CHECK (status IN ('draft', 'approved', 'archived')),
  CONSTRAINT content_variant_unique
    UNIQUE (offer_id, language, kind, platform, variant_key, version)
);

CREATE INDEX IF NOT EXISTS idx_content_variants_offer
  ON content_variants (offer_id, language, kind, status);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'schedules_content_variant_fk'
  ) THEN
    ALTER TABLE schedules
      ADD CONSTRAINT schedules_content_variant_fk
      FOREIGN KEY (content_variant_id) REFERENCES content_variants(id)
      ON DELETE SET NULL;
  END IF;
END $$;

-- --------------------------------------------------------- experiments
CREATE TABLE IF NOT EXISTS content_experiments (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id      UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
  schedule_id   UUID REFERENCES schedules(id) ON DELETE SET NULL,
  variant_id    UUID REFERENCES content_variants(id) ON DELETE SET NULL,
  language      TEXT NOT NULL DEFAULT 'en',
  platform      TEXT,
  hypothesis    TEXT NOT NULL,
  metric        TEXT NOT NULL DEFAULT 'views',
  status        TEXT NOT NULL DEFAULT 'running',
  result        JSONB NOT NULL DEFAULT '{}',
  created_by    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT experiment_status_check
    CHECK (status IN ('planned', 'running', 'won', 'lost', 'inconclusive'))
);

CREATE INDEX IF NOT EXISTS idx_experiments_offer
  ON content_experiments (offer_id, status, created_at DESC);

-- Seed the brand identity defaults (idempotent; operator can edit in Settings).
INSERT INTO settings (key, value, updated_by)
VALUES (
  'brand',
  '{"name": "MTK RADAR", "website_url": "", "cta": "Full guide + source links in the description", "default_language": "en", "languages": ["en", "ur"], "hashtag_sets": {}}'::jsonb,
  'migration:020'
)
ON CONFLICT (key) DO NOTHING;

INSERT INTO settings (key, value, updated_by)
VALUES (
  'media_backup',
  '{"enabled": false, "schedule": "daily", "retention_days": 14, "last_run_at": null, "last_status": "not_configured"}'::jsonb,
  'migration:020'
)
ON CONFLICT (key) DO NOTHING;
