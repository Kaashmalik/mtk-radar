-- WP01: preserve the exact text the extractor saw. NULL means legacy evidence
-- whose bytes were never retained; do not invent or backfill historical text.
ALTER TABLE evidence ADD COLUMN captured_content TEXT;

ALTER TABLE evidence ADD CONSTRAINT evidence_snapshot_integrity CHECK (
    captured_content IS NULL OR (
        length(btrim(captured_content)) > 0
        AND octet_length(captured_content) <= 1000000
        AND content_hash = encode(digest(captured_content, 'sha256'), 'hex')
    )
);

-- Distinct URLs must not share an evidence identity merely because their text
-- matches. A fresh snapshot may coexist with a legacy hash-only row; repeat
-- new submissions still dedupe without mutating historical evidence.
DROP INDEX uq_evidence_offer_hash;
CREATE UNIQUE INDEX uq_evidence_offer_url_hash_snapshot
    ON evidence (offer_id, url, content_hash, (captured_content IS NOT NULL), official, source_id)
    NULLS NOT DISTINCT;
