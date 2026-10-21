"""Per-source terms-of-service attestation validity (WP01 slice 11).

A review is a statement about a provider's terms at a point in time. Terms
change, so the decision must not last forever: the API and the worker derive the
same expiry from the recorded review timestamp and a bounded deployment policy,
and both stop authorising new collection once it passes. There is no stored
expiry column to drift — the policy is one number, documented in `.env.example`.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

#: Default validity of a review. Long enough not to nag, short enough that a
#: changed terms page is re-read within a release cycle.
DEFAULT_TTL_DAYS = 180
#: Absurd values are clamped rather than silently trusted.
MAX_TTL_DAYS = 3650


def ttl_days() -> int:
    """The deployment's review validity in days (1..3650, default 180)."""
    raw = os.environ.get("MTK_TOS_REVIEW_TTL_DAYS", str(DEFAULT_TTL_DAYS)).strip()
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_TTL_DAYS
    return max(1, min(days, MAX_TTL_DAYS))


def expires_at(reviewed_at: Optional[datetime],
               days: Optional[int] = None) -> Optional[datetime]:
    """When an attestation recorded at `reviewed_at` stops authorising reads."""
    if reviewed_at is None:
        return None
    return reviewed_at + timedelta(days=ttl_days() if days is None else days)


def is_valid(reviewed_at: Optional[datetime], now: Optional[datetime] = None,
             days: Optional[int] = None) -> bool:
    """True only for a recorded review that has not expired."""
    expires = expires_at(reviewed_at, days)
    if expires is None:
        return False
    return expires > (now or datetime.now(timezone.utc))
