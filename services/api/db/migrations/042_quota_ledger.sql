-- 2026-10-28 plan (Q1): platform API quota reservation ledger.
--
-- YouTube Data API quota resets at midnight Pacific time and failed or
-- retried requests are NOT free. Every upload package reserves its
-- predicted units BEFORE the first request; the reservation is consumed
-- when a request may have been sent, released only when none was.
CREATE TABLE IF NOT EXISTS quota_ledger (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider    TEXT NOT NULL,                 -- 'youtube'
  bucket      TEXT NOT NULL,                 -- 'units' | 'uploads'
  account     TEXT NOT NULL DEFAULT 'default',
  quota_day   DATE NOT NULL,                 -- the provider's reset day
  units       INTEGER NOT NULL CHECK (units >= 0),
  status      TEXT NOT NULL DEFAULT 'reserved'
                CHECK (status IN ('reserved', 'consumed', 'released')),
  operation   TEXT,                          -- e.g. 'upload_package'
  ref_type    TEXT,
  ref_id      TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  settled_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_quota_ledger_day
  ON quota_ledger (provider, bucket, account, quota_day)
  WHERE status <> 'released';
