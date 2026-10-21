-- WP01: per-source terms-of-service review attestation (slice 10).
--
-- robots.txt is a machine-checkable technical permission; it is not consent
-- under a provider's terms. This records the human decision that automated
-- reading of a source is permitted, who made it, when, and what they reviewed.
-- All three columns are set together or not at all: a timestamp without a named
-- reviewer is not an attestation.
--
-- Nullable for pre-018 sources. The API refuses new machine-collected evidence
-- for a source without an attestation (MTK_REQUIRE_TOS_ATTESTATION, default on);
-- existing evidence is not rewritten.
ALTER TABLE sources
  ADD COLUMN tos_reviewed_at TIMESTAMPTZ,
  ADD COLUMN tos_reviewer TEXT,
  ADD COLUMN tos_reference TEXT,
  ADD CONSTRAINT sources_tos_review_complete CHECK (
    (tos_reviewed_at IS NULL AND tos_reviewer IS NULL AND tos_reference IS NULL)
    OR (
      tos_reviewed_at IS NOT NULL
      AND tos_reviewer IS NOT NULL AND btrim(tos_reviewer) <> ''
      AND tos_reference IS NOT NULL AND btrim(tos_reference) <> ''
    )
  );
