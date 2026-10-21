-- WP01: sign fetch provenance with the deployment's acquisition key
-- (master plan §6 steps 2-3). `fetch_identity` is a caller-chosen string; the
-- signature is what binds a machine evidence record to the process that holds
-- the key.
--
-- No "raw bytes imply a signature" constraint here: MTK_REQUIRE_FETCH_SIGNATURE=0
-- is a documented opt-out for migrating legacy deployments, and a hard CHECK
-- would make that opt-out unusable. Ingest and the promotion gate enforce the
-- requirement instead, so opting out is explicit and visible.
ALTER TABLE evidence ADD COLUMN fetch_signature TEXT;

ALTER TABLE evidence ADD CONSTRAINT evidence_fetch_signature_shape CHECK (
    fetch_signature IS NULL OR fetch_signature ~ '^[0-9a-f]{64}$'
);
