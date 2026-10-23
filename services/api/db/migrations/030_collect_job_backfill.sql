-- v0.33: durable collection backfill.
--
-- Sources predating the collect job contract (028/029 era) had no durable
-- "this source owes a poll" record — the collector's in-memory cadence dict
-- was the only driver, so a worker restart silently dropped every source
-- until the next list sweep. This backfills a collect job per ENABLED
-- source, keyed by the same dedupe format source creation uses
-- (collect:{id}) so backfill and enqueue can never double-record one source.
--
-- run_after = now(): the first claim happens at the next collector sweep;
-- after that, only poll-results re-arm the job with the source's cadence,
-- so cadence stays owned by actual poll outcomes, not by re-application.
-- max_attempts = 5 mirrors the recurring-job contract: 5 claims without a
-- healthy poll-result dead-letter the job into operator attention.

INSERT INTO jobs (kind, entity_id, payload, run_after, max_attempts, dedupe_key)
SELECT 'collect',
       s.id,
       jsonb_build_object('provider', s.provider, 'adapter', s.adapter),
       now(),
       5,
       'collect:' || s.id::text
FROM sources s
WHERE s.enabled
ON CONFLICT (dedupe_key) DO NOTHING;
