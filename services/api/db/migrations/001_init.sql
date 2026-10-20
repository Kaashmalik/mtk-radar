-- MTK RADAR AI — core schema (Week 1)
-- Implements master plan §10: Sources, Items, Offers, Evidence, Projects, Approvals, Schedules.
-- Offer lifecycle (§3): candidate → evidence_needed → verified → approved_for_video
--   → published → expired | corrected. Video generation blocked before 'verified'.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE trust_tier AS ENUM ('A_provider_owned', 'B_discovery_lead', 'C_excluded');

CREATE TYPE offer_state AS ENUM (
  'candidate', 'evidence_needed', 'verified', 'approved_for_video',
  'published', 'expired', 'corrected'
);

CREATE TYPE schedule_state AS ENUM (
  'draft', 'needs_approval', 'approved', 'scheduled', 'published', 'failed', 'paused'
);

CREATE TYPE project_state AS ENUM ('draft', 'in_review', 'approved', 'stale', 'retired');

-- §10 Sources: registry, not a scraping free-for-all.
CREATE TABLE sources (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider      TEXT NOT NULL,
  canonical_domain TEXT,                    -- e.g. huggingface.co
  account_handle TEXT,                      -- official account, if applicable
  category      TEXT NOT NULL,              -- model_hubs | dev_platforms | student_programs | ...
  adapter       TEXT NOT NULL,              -- 'rss' | 'github_releases' | 'page_watch' | 'manual'
  config        JSONB NOT NULL DEFAULT '{}',
  enabled       BOOLEAN NOT NULL DEFAULT TRUE,
  polling_cadence INTERVAL NOT NULL DEFAULT '6 hours',
  country_scope TEXT[] NOT NULL DEFAULT '{}',
  trust_tier    trust_tier NOT NULL DEFAULT 'B_discovery_lead',
  last_checked_at TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §10 Items: every observed source event, deduplicated.
CREATE TABLE items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id       UUID NOT NULL REFERENCES sources(id),
  external_item_id TEXT NOT NULL,           -- stable id from the source
  url             TEXT NOT NULL,
  canonical_url   TEXT,
  title           TEXT,
  observed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at    TIMESTAMPTZ,
  text_hash       TEXT NOT NULL,            -- sha256 of normalized text
  duplicate_group TEXT,                     -- groups cross-source duplicates
  processed       BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (source_id, external_item_id)
);

-- §10 Offers: the offer record schema (§3) as time-sensitive data.
CREATE TABLE offers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title           TEXT NOT NULL,
  provider        TEXT NOT NULL,
  category        TEXT NOT NULL,
  offer_type      TEXT NOT NULL,            -- free_trial | credits | student_perk | model_access | ...
  eligibility     JSONB NOT NULL DEFAULT '{}',   -- country, student/status, new-customer rule
  value           JSONB NOT NULL DEFAULT '{}',   -- currency, amount, cap, duration, exclusions
  claim_steps     JSONB NOT NULL DEFAULT '[]',   -- ordered steps incl. command cards
  promo_code      TEXT,
  redemption_url  TEXT,
  starts_at       TIMESTAMPTZ,
  expires_at      TIMESTAMPTZ,
  timezone        TEXT NOT NULL DEFAULT 'Asia/Karachi',
  renewal         JSONB NOT NULL DEFAULT '{}',   -- auto_renew, price, payment_required
  state           offer_state NOT NULL DEFAULT 'candidate',
  confidence      NUMERIC(3,2) NOT NULL DEFAULT 0.00,
  recheck_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  correction_note TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §3/§10 Evidence: immutable snapshots; each field links to its source.
CREATE TABLE evidence (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id         UUID NOT NULL REFERENCES offers(id),
  source_id        UUID REFERENCES sources(id),
  url              TEXT NOT NULL,
  captured_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  content_hash     TEXT NOT NULL,           -- sha256 of captured content
  excerpt          TEXT,                    -- supporting quote
  screenshot_path  TEXT,                    -- object storage key; redacted before use
  supported_fields JSONB NOT NULL DEFAULT '[]' , -- which offer fields this proves
  reviewer         TEXT,
  review_note      TEXT
);

-- §10 Projects: video project per offer.
CREATE TABLE projects (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id        UUID NOT NULL REFERENCES offers(id),
  state           project_state NOT NULL DEFAULT 'draft',
  script_version  INTEGER NOT NULL DEFAULT 1,
  script_path     TEXT,                     -- versioned script.md
  capture_path    TEXT,                     -- object storage key
  render_paths    JSONB NOT NULL DEFAULT '{}',  -- 16:9, 9:16, captions, thumbnail
  disclosure_meta JSONB NOT NULL DEFAULT '{}',  -- synthetic/label metadata
  version_hash    TEXT,                     -- hash of the exact approved content
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §10 Approvals: recorded with user, time, and exact version hash.
CREATE TABLE approvals (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES projects(id),
  approver      TEXT NOT NULL,
  version_hash  TEXT NOT NULL,
  approved_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  note          TEXT,
  UNIQUE (project_id, version_hash)
);

-- §10/§17 Schedules: publish queue with retries and idempotency.
CREATE TABLE schedules (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id),
  platform        TEXT NOT NULL,            -- youtube | facebook | instagram | tiktok
  state           schedule_state NOT NULL DEFAULT 'draft',
  local_time      TIMESTAMPTZ NOT NULL,
  timezone        TEXT NOT NULL DEFAULT 'Asia/Karachi',
  caption_variant TEXT NOT NULL DEFAULT 'default',
  privacy         TEXT NOT NULL DEFAULT 'private',
  idempotency_key TEXT NOT NULL UNIQUE,
  retry_count     INTEGER NOT NULL DEFAULT 0,
  remote_post_id  TEXT,
  outcome_detail  JSONB NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §0/§10 Audit trail: who did what, when, on which version.
CREATE TABLE audit_log (
  id           BIGSERIAL PRIMARY KEY,
  actor        TEXT NOT NULL,
  action       TEXT NOT NULL,
  entity       TEXT NOT NULL,
  entity_id    UUID,
  version_hash TEXT,
  detail       JSONB NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_items_canonical ON items(canonical_url);
CREATE INDEX idx_items_hash ON items(text_hash);
CREATE INDEX idx_offers_state ON offers(state);
CREATE INDEX idx_offers_recheck ON offers(recheck_at) WHERE state IN ('verified', 'approved_for_video', 'published');
CREATE INDEX idx_evidence_offer ON evidence(offer_id);
CREATE INDEX idx_schedules_state ON schedules(state, local_time);

-- Guard: block schedules referencing a project whose offer expired/needs recheck.
CREATE VIEW schedulable_offers AS
SELECT o.id AS offer_id, p.id AS project_id, p.version_hash
FROM offers o
JOIN projects p ON p.offer_id = o.id
WHERE o.state = 'approved_for_video'
  AND o.recheck_at <= now()
  AND p.state = 'approved'
  AND (o.expires_at IS NULL OR o.expires_at > now());
