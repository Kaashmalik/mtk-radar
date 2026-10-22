-- v0.31: metrics provenance and degradation records (enhancement plan §7.F.3-F.6).
--
-- A stored audience number is only useful if an operator can answer: which
-- reporting period produced it, under which metric definition, and did the
-- provider reject part of the request? Previously only `source` and
-- `captured_at` existed, so an unsupported-metric fallback was invisible and
-- a nearest-bucket retention value could not be distinguished from an exact
-- measurement.

ALTER TABLE post_metrics
  ADD COLUMN IF NOT EXISTS report_start DATE,
  ADD COLUMN IF NOT EXISTS report_end DATE,
  ADD COLUMN IF NOT EXISTS metric_definition TEXT,
  ADD COLUMN IF NOT EXISTS degraded BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS degradation_detail TEXT,
  -- True when retention_3s came from the nearest elapsedVideoTimeRatio bucket
  -- rather than an exact 3-second measurement. The UI must qualify it.
  ADD COLUMN IF NOT EXISTS retention_3s_estimated BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN post_metrics.report_start IS
  'First day covered by the provider report (null when unknown).';
COMMENT ON COLUMN post_metrics.report_end IS
  'Last day covered by the provider report (null when unknown).';
COMMENT ON COLUMN post_metrics.degraded IS
  'True when at least one metric group was rejected and omitted.';
COMMENT ON COLUMN post_metrics.retention_3s_estimated IS
  'True when retention_3s is a nearest-bucket estimate, not exact.';
