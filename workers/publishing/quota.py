"""YouTube quota planning + reservation client (Q1, 2026-10-28 plan).

The worker reserves the WHOLE package's predicted quota before the first
YouTube request, so a day cannot end with a video uploaded but its
thumbnail/captions refused for quota. Costs are env-overridable and should
mirror the project's Google Cloud console; defaults are the long-documented
conservative values (an upload has historically cost 1600 units).

Fail-closed: if the reservation cannot be confirmed, nothing is uploaded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import httpx

#: operation → (env override, default units)
COSTS: dict[str, tuple[str, int]] = {
    "upload": ("YOUTUBE_QUOTA_COST_UPLOAD", 1600),
    "thumbnail": ("YOUTUBE_QUOTA_COST_THUMBNAIL", 50),
    "captions": ("YOUTUBE_QUOTA_COST_CAPTIONS", 400),
    "playlist": ("YOUTUBE_QUOTA_COST_PLAYLIST", 50),
    "comment": ("YOUTUBE_QUOTA_COST_COMMENT", 50),
    # videos.list polls while confirming processing/privacy (1 unit each).
    "status_polls": ("YOUTUBE_QUOTA_COST_STATUS_POLLS", 60),
}


def cost(operation: str) -> int:
    env, default = COSTS[operation]
    try:
        return max(0, int(os.environ.get(env, default)))
    except ValueError:
        return default


def youtube_package_units(*, thumbnail: bool, captions: bool, playlist: bool,
                          comment: bool) -> dict[str, int]:
    """Bucket → units for one complete YouTube package."""
    units = cost("upload") + cost("status_polls")
    units += cost("thumbnail") if thumbnail else 0
    units += cost("captions") if captions else 0
    units += cost("playlist") if playlist else 0
    units += cost("comment") if comment else 0
    return {"units": units, "uploads": 1}


@dataclass
class Reservation:
    allowed: bool
    reservation_id: Optional[str] = None
    retry_after_s: Optional[int] = None
    reason: str = ""


def reserve(api: httpx.Client, *, account: str, buckets: dict[str, int],
            schedule_id: str) -> Reservation:
    try:
        resp = api.post("/quota/reserve", json={
            "provider": "youtube", "account": account or "default",
            "buckets": buckets, "operation": "upload_package",
            "ref_type": "schedule", "ref_id": str(schedule_id)})
    except httpx.HTTPError as exc:
        return Reservation(False, reason=f"quota ledger unreachable ({type(exc).__name__})")
    if resp.status_code == 404:
        # Older API without the ledger: keep the previous behaviour.
        return Reservation(True, reason="quota ledger not available on this API")
    if resp.status_code != 200:
        return Reservation(False, reason=f"quota reservation refused (HTTP {resp.status_code})")
    try:
        body = resp.json()
    except ValueError:
        return Reservation(False, reason="quota reservation returned no JSON")
    if body.get("allowed") is True and body.get("reservation_id"):
        return Reservation(True, body["reservation_id"])
    buckets_state = body.get("buckets") or {}
    short = ", ".join(f"{b}: {s.get('remaining')} left of {s.get('limit')}"
                      for b, s in buckets_state.items() if not s.get("allowed"))
    return Reservation(False, retry_after_s=body.get("retry_after_s"),
                       reason=f"YouTube daily quota would be exceeded ({short}); "
                              f"resets at {body.get('resets_at')}")


def settle(api: httpx.Client, reservation_id: Optional[str], *, sent: bool) -> None:
    """consumed when any request may have been sent; released otherwise."""
    if not reservation_id:
        return
    try:
        api.post(f"/quota/{reservation_id}/settle",
                 json={"status": "consumed" if sent else "released"})
    except httpx.HTTPError:
        # An unsettled reservation keeps counting as used: conservative.
        pass
