-- 2026-10-28 plan: storyboard editor (V7) + public-page capture worker (M2).
--
-- `storyboards` holds the reviewer's scene selection for an explainer: one
-- row per VERSION (a save supersedes, never rewrites), validated against the
-- claim ledger on save and again at render time.
CREATE TABLE IF NOT EXISTS storyboards (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id    UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
  version     INTEGER NOT NULL,
  scenes      JSONB NOT NULL,
  sha256      TEXT NOT NULL,
  brief_id    UUID REFERENCES research_briefs(id) ON DELETE SET NULL,
  created_by  TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (offer_id, version)
);

-- `page_captures` are screenshots of PUBLIC pages taken by the sandboxed
-- page-capture worker (fresh browser context, public-IP egress only,
-- robots.txt honoured). They become `page` scenes in the storyboard.
CREATE TABLE IF NOT EXISTS page_captures (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  offer_id     UUID NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
  url          TEXT NOT NULL,
  final_url    TEXT,
  title        TEXT,
  status       TEXT NOT NULL DEFAULT 'requested'
                 CHECK (status IN ('requested', 'ok', 'failed', 'refused')),
  detail       TEXT,
  image_ref    TEXT,
  image_sha256 TEXT,
  http_status  INTEGER,
  requested_by TEXT,
  captured_at  TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_page_captures_offer
  ON page_captures (offer_id, created_at DESC);
