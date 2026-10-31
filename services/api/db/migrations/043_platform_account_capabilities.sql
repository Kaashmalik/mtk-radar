-- 2026-10-28 plan (G23 UX): live platform capabilities per account.
--
-- TikTok Direct Post must show the creator's CURRENT creator_info (handle,
-- offered privacy levels, disabled interactions, max duration) before the
-- operator consents. Only the publishing worker holds the credentials, so it
-- refreshes this snapshot; the dashboard reads it. No tokens are stored.
ALTER TABLE platform_accounts
  ADD COLUMN IF NOT EXISTS capabilities JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS capabilities_checked_at TIMESTAMPTZ;
