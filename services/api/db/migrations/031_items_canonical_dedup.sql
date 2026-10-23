-- 030: enforce the documented items dedup guarantee.
--
-- The ingest contract says a candidate appears EXACTLY ONCE — keyed by
-- (source_id, external_item_id) AND by the canonical URL + text hash. Only the
-- first key had a unique constraint, so a resubmission with a fresh
-- external_item_id (common for scrapers/extension re-runs) silently created a
-- second row and double-counted in the radar and attention counts. This index
-- makes the second key real; create_item now relies on it via a
-- target-free ON CONFLICT DO NOTHING.
--
-- Existing duplicates (pre-constraint rows) are collapsed first, keeping the
-- OLDEST row per (canonical_url, text_hash) so observed_at history survived.

DELETE FROM items a
USING items b
WHERE a.canonical_url IS NOT NULL
  AND a.text_hash IS NOT NULL
  AND a.canonical_url = b.canonical_url
  AND a.text_hash = b.text_hash
  AND a.ctid > b.ctid;

CREATE UNIQUE INDEX IF NOT EXISTS items_canonical_text_hash_key
  ON items (canonical_url, text_hash)
  WHERE canonical_url IS NOT NULL AND text_hash IS NOT NULL;
