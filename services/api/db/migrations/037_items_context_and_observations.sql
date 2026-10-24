-- EP-02 G07/G08: persist what an observation actually SAW.
--
-- Items used to store only a text HASH: the excerpt, the browser selection,
-- the account handle and the adapter's typed payload (RawItem.extra) were
-- dropped at intake, yet they feed the dedup hash — so the radar could
-- never re-score the body that produced a candidate, and later engagement
-- counts (HN points, HF upvotes, stars) CONFLICTED with the UNIQUE item key
-- and disappeared instead of accumulating as a time series.

ALTER TABLE items
  ADD COLUMN IF NOT EXISTS text TEXT,
  ADD COLUMN IF NOT EXISTS selection TEXT,
  ADD COLUMN IF NOT EXISTS account_handle TEXT,
  ADD COLUMN IF NOT EXISTS extra JSONB NOT NULL DEFAULT '{}';

-- Typed raw observations: APPEND-ONLY measurements with retrieval time,
-- source identity, canonical entity, payload hash and provenance. Story
-- dedup stays in `items` (UNIQUE keys there decide whether a CANDIDATE
-- exists); this table only accumulates what was measured, when, by whom.
-- Raw count deltas between consecutive rows drive momentum (G08) — a
-- missing measurement is simply absent, never interpolated.
CREATE TABLE IF NOT EXISTS source_observations (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id     UUID REFERENCES sources(id) ON DELETE SET NULL,
  adapter       TEXT NOT NULL,               -- rss | hn_search | reddit_new | ...
  external_id   TEXT NOT NULL,               -- the source's stable entity id
  entity_key    TEXT NOT NULL,               -- '<adapter>:<external_id>' — same entity across re-fetches
  url           TEXT,                        -- canonical URL when known
  observed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),   -- retrieval time
  measurements  JSONB NOT NULL DEFAULT '{}', -- typed: points, comments, upvotes, stars (numbers only)
  payload_hash  TEXT NOT NULL,               -- sha256 of the observed payload (extra + excerpt)
  excerpt       TEXT,                        -- bounded context the hash covers
  provenance    JSONB NOT NULL DEFAULT '{}'  -- recorded facts: source_kind, trust tier, intake path
);

CREATE INDEX IF NOT EXISTS idx_source_observations_entity
  ON source_observations (entity_key, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_observations_url
  ON source_observations (url, observed_at DESC);

-- Literally append-only: measurements are facts of a moment in time; editing
-- or deleting them would rewrite what the radar observed (and could fake a
-- rising trend). Corrections are NEW observations.
CREATE OR REPLACE FUNCTION forbid_source_observation_mutation()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'source_observations is append-only (% attempted)',
    TG_OP;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS source_observations_append_only ON source_observations;
CREATE TRIGGER source_observations_append_only
  BEFORE UPDATE OR DELETE ON source_observations
  FOR EACH ROW EXECUTE FUNCTION forbid_source_observation_mutation();
