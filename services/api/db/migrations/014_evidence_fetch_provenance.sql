-- WP01: preserve the exact bytes a provider served, plus the fetch provenance
-- that produced them (master plan §6 steps 2-3, audit A19). Legacy rows stay
-- NULL: do not invent provenance for evidence whose bytes were never retained.
ALTER TABLE evidence
    ADD COLUMN raw_content BYTEA,
    ADD COLUMN raw_hash TEXT,
    ADD COLUMN requested_url TEXT,
    ADD COLUMN fetch_status INT,
    ADD COLUMN fetch_content_type TEXT,
    ADD COLUMN fetched_at TIMESTAMPTZ,
    ADD COLUMN fetch_redirects JSONB,
    ADD COLUMN parser_version TEXT,
    ADD COLUMN fetch_identity TEXT;

-- Raw bytes are only useful if they are intact and attributable.
ALTER TABLE evidence ADD CONSTRAINT evidence_raw_snapshot_integrity CHECK (
    raw_content IS NULL OR (
        octet_length(raw_content) BETWEEN 1 AND 2000000
        AND raw_hash = encode(digest(raw_content, 'sha256'), 'hex')
        AND requested_url IS NOT NULL
        AND fetched_at IS NOT NULL
        AND parser_version IS NOT NULL
    )
);

ALTER TABLE evidence ADD CONSTRAINT evidence_fetch_status_range CHECK (
    fetch_status IS NULL OR fetch_status BETWEEN 100 AND 599
);
