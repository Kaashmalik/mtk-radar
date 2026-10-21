-- WP01: record the provider's robots.txt decision with every machine-collected
-- official snapshot (master plan §3, §6 step 2). A politeness delay is not
-- permission: the bytes may only become evidence when the policy was readable
-- and permitted the read, and the decision must not postdate the fetch.
--
-- Legacy rows stay NULL: their permission was never obtained, so it must not be
-- invented. Reviewer-attested evidence also has no robots decision.
ALTER TABLE evidence
    ADD COLUMN robots_url TEXT,
    ADD COLUMN robots_checked_at TIMESTAMPTZ,
    ADD COLUMN robots_allowed BOOLEAN,
    ADD COLUMN robots_status INT;

-- Either the whole robots record exists or none of it does.
ALTER TABLE evidence ADD CONSTRAINT evidence_robots_record_complete CHECK (
    (robots_url IS NULL AND robots_checked_at IS NULL
        AND robots_allowed IS NULL AND robots_status IS NULL)
    OR (robots_url IS NOT NULL AND robots_checked_at IS NOT NULL
        AND robots_allowed IS NOT NULL)
);

-- Retained raw bytes imply a permitted read. A disallowed fetch must never have
-- produced a stored snapshot in the first place. NOT VALID: rows captured
-- between migrations 014 and 015 legitimately have bytes but no permission
-- record yet; they stay readable, are re-checked by the promotion gate, and
-- every new or updated row must satisfy the constraint.
ALTER TABLE evidence ADD CONSTRAINT evidence_raw_snapshot_permitted CHECK (
    raw_content IS NULL OR robots_allowed IS TRUE
) NOT VALID;

ALTER TABLE evidence ADD CONSTRAINT evidence_robots_status_range CHECK (
    robots_status IS NULL OR robots_status BETWEEN 100 AND 599
);
