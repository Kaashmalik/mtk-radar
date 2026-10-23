-- v0.33: durable publish_jobs backfill.
--
-- 028 introduced the jobs table, but every post already sitting in
-- state='scheduled' predates it: their "owed publishing work" had no durable
-- record, so a wedged/never-claimed post was invisible to the queue view.
-- This backfills a publish_schedule job per still-owed post, keyed by the
-- SAME dedupe format schedule creation uses (publish:{id}:{package_hash}) so
-- backfill and enqueue can never double-record one post.
--
-- Also aligns run_after with the actual publish time for every pending job:
-- the creation path originally defaulted run_after to now(), which made the
-- queue wake workers for posts that were not due yet.
--
-- max_attempts = 20: each failed attempt consumes one; the worker's
-- not-due-yet re-check re-queues with retry_after (≤1 day per re-check), so
-- 20 covers ~3 weeks of a far-future post plus real retries, before the job
-- dead-letters into operator attention.

INSERT INTO jobs (kind, entity_id, payload, run_after, max_attempts, dedupe_key)
SELECT 'publish_schedule',
       s.id,
       jsonb_build_object('platform', s.platform, 'language', s.language,
                          'package_hash', s.package_hash),
       COALESCE(s.local_time, now()),
       20,
       'publish:' || s.id::text || ':' || COALESCE(s.package_hash, '')
FROM schedules s
WHERE s.state = 'scheduled'
ON CONFLICT (dedupe_key) DO NOTHING;

-- Existing pending jobs: point run_after at the publish time instead of the
-- moment they were enqueued (idempotent: rows already aligned just rewrite
-- the same timestamp).
UPDATE jobs j
SET run_after = s.local_time, updated_at = now()
FROM schedules s
WHERE j.kind = 'publish_schedule'
  AND j.entity_id = s.id
  AND j.status = 'pending'
  AND s.local_time IS NOT NULL;
