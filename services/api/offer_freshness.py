"""Offer freshness at action boundaries (WP01 slice 12).

`verified` is not a permanent fact: it carries an expiry and a recheck deadline,
and the transition to `verified` sets the deadline. Scheduling and the publishing
worker already refuse an overdue offer; capture and resume did not, so footage
could be recorded or a paused post re-queued for an offer nobody had rechecked.
This module is the single read those boundaries use, so the reasons stay
consistent and fail closed: a missing `recheck_at` is overdue, never fresh.
"""

from __future__ import annotations

import uuid
from typing import Optional


async def freshness_problem(pool, offer_id: uuid.UUID) -> Optional[str]:
    """Why this offer may not be acted on now, or None when it is still fresh.

    Does not consider the offer's state; callers that need it check that
    separately (captures: video-allowed states, resume: `_revalidate_offer`).
    """
    row = await pool.fetchrow(
        """
        SELECT (expires_at IS NULL OR expires_at > now()) AS not_expired,
               recheck_at > now() AS recheck_ok
        FROM offers WHERE id = $1
        """,
        offer_id,
    )
    if row is None:
        return "offer not found"
    if not row["not_expired"]:
        return "offer has expired"
    if not row["recheck_ok"]:
        return "offer recheck is overdue (recheck_at)"
    return None
