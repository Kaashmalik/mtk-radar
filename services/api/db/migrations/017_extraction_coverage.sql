-- WP01: record what the extractor actually examined (WP01 slice 8).
--
-- `coverage` names the snapshots that were sectioned and how many sections the
-- document was split into. The API recomputes that count from the stored
-- snapshot text before accepting a new record, so a truncated read cannot claim
-- full coverage. Nullable on purpose: proposals written before 017 (and manual
-- reviewer extraction) carry no coverage claim, and the API never invents one.
ALTER TABLE extractions ADD COLUMN coverage JSONB;
