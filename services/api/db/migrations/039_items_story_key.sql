-- EP-02 G09: cross-URL same-story clustering.
--
-- Corroboration grouped by duplicate_group = the canonical URL, so the SAME
-- story republished at a different URL (syndication, mirror, updated
-- permalink) was invisible to the "how many independent sources saw this"
-- count. items.story_key clusters by normalized headline; corroboration
-- counts DISTINCT providers across the WHOLE story cluster.
--
-- story_key is a signal-aggregation key only — items dedup rules (the
-- UNIQUE (source_id, external_item_id) key and the (canonical_url,
-- text_hash) index) are untouched.

ALTER TABLE items
  ADD COLUMN IF NOT EXISTS story_key TEXT;

CREATE INDEX IF NOT EXISTS idx_items_story_key
  ON items (COALESCE(story_key, duplicate_group));
