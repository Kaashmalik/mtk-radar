"""Publishing worker — scheduled multi-platform uploads.

Weeks 9-10 target (master plan §18): a private/test upload and token-expiry
recovery are verified.

Hard rules (master plan §6/§17):
- Schedule belongs in the dashboard; each queued post references an approved
  video version AND a valid offer evidence snapshot.
- Revalidate the offer before upload and again right before publish; auto-pause
  affected posts if the offer expires or changes.
- Retries must use idempotency keys (unique in DB) with backoff; a manual
  pause/cancel control is always operator-visible.
- Never automate browser clicks to evade platform API rules. Official APIs
  only: YouTube Data API, Meta Graph API, TikTok Content Posting API,
  with Postiz as an optional integration (AGPL obligations reviewed).
"""

# Queue states: draft → needs_approval → approved → scheduled → published|failed|paused

if __name__ == "__main__":
    raise NotImplementedError("publish adapters not implemented yet (weeks 9-11)")
