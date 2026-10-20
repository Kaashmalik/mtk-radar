-- Week 10: Publishing integrations (master plan §6, §18)
-- "Connect YouTube and one additional platform through official APIs... 
--  A private/test upload and token-expiry recovery are verified."

-- OAuth/credential REFERENCES only — raw tokens never enter the database
-- (master plan §7: secrets live in a vault/environment manager).
CREATE TABLE platform_accounts (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  platform          TEXT NOT NULL,               -- 'youtube' | 'facebook' | ...
  account_handle    TEXT NOT NULL,
  credential_source TEXT NOT NULL,               -- 'env:PREFIX' | 'vault:<path>'
  scopes            TEXT[] NOT NULL DEFAULT '{}',
  status            TEXT NOT NULL DEFAULT 'active',  -- active | token_expired | revoked
  expires_at        TIMESTAMPTZ,                 -- token expiry (reported, never the token)
  last_refreshed_at TIMESTAMPTZ,
  last_error        TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (platform, account_handle)
);
