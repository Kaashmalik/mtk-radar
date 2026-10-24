-- v0.37: Usage ledger + shared cache (WP-F, enhancement plan 2026-10-24 §5.5).
--
-- `usage_events` is the money ledger: every metered spend (LLM extraction,
-- TTS synthesis, trend fetches, YouTube quota units) lands here before or
-- right after it happens, so the Costs card and the per-day budgets answer
-- from data, not guesses. Events are append-only; cost_usd_est is an
-- ESTIMATE priced from env knobs at ingest — never a confirmation.
CREATE TABLE IF NOT EXISTS usage_events (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind          TEXT NOT NULL,               -- llm_extract | tts | trend_fetch | youtube_quota
  provider      TEXT NOT NULL DEFAULT '',
  model         TEXT NOT NULL DEFAULT '',
  units         BIGINT NOT NULL DEFAULT 0,
  unit_type     TEXT NOT NULL DEFAULT 'units', -- tokens | chars | requests | quota_units
  cost_usd_est  NUMERIC(12,6) NOT NULL DEFAULT 0,
  ref_type      TEXT,                        -- offer | schedule | source | video | ...
  ref_id        UUID,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  meta          JSONB NOT NULL DEFAULT '{}'  -- tokens_in/out, cache_hit, blocked, source, endpoint
);

CREATE INDEX IF NOT EXISTS idx_usage_events_day
  ON usage_events (kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_events_recent
  ON usage_events (created_at DESC);

-- `cache_entries` is the Postgres fallback layer of the shared cache
-- (Redis-first, Postgres second, per-process memory last). The API and the
-- workers reach the SAME entries: the workers go over HTTP
-- (/costs/cache-*), the API reads this table + Redis directly — so a
-- re-verification (or re-render) done by one process is free for all.
CREATE TABLE IF NOT EXISTS cache_entries (
  key         TEXT PRIMARY KEY,              -- namespaced: "extract:<model>:<sha>"
  value       JSONB NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cache_entries_expiry ON cache_entries (expires_at);
