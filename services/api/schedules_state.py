"""Schedule queue state machine + platform metadata (master plan §17).

Queue states (§17 table):
    Draft → Needs approval → Approved → Scheduled → Published / Failed / Paused

Rules enforced:
- Approved requires a recorded reviewer AND the exact approved version hash.
- Scheduled re-validates that the CURRENT script hash still equals the approved
  hash — material edits after approval force reapproval (rollback safety).
- Pause is always available to the operator; resume revalidates the hash too.
- Published/failed results are recorded by the publishing worker, never assumed.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Final

from jsonb import decode_mapping
from seo import PLATFORM_LIMITS, PLATFORMS, build_metadata

SCHEDULE_STATES: Final[tuple[str, ...]] = (
    "draft", "needs_approval", "approved", "scheduled",
    "published", "failed", "paused",
)

TRANSITIONS: Final[dict[str, tuple[str, ...]]] = {
    "draft": ("needs_approval", "paused"),
    "needs_approval": ("approved", "draft"),
    "approved": ("scheduled", "needs_approval", "paused"),
    "scheduled": ("published", "failed", "paused"),
    "paused": ("scheduled", "failed"),  # resume, or operator cancels as failed
    "published": (),                     # terminal — corrections create new content
    "failed": ("scheduled", "paused"),   # retry eligible failures only
}

# Plan §6/§17: official-API constraints live in seo.py (single source of
# truth shared by the schedule API, the studio and the publishing adapters).
REVIEW_REQUIRED: Final[frozenset[str]] = frozenset({"approved"})


def can_transition(from_state: str, to_state: str) -> bool:
    return to_state in TRANSITIONS.get(from_state, ())


class ScheduleTransitionError(ValueError):
    pass


def script_version_hash(markdown: str) -> str:
    """Approval binds to the EXACT script content; any edit changes the hash."""
    import hashlib

    return hashlib.sha256((markdown or "").encode("utf-8")).hexdigest()


def validate_transition(from_state: str, to_state: str, *, reviewer: str | None,
                        version_hash: str | None) -> str:
    """Raise unless the transition is legal and carries its required context.
    Returns the (possibly missing) version_hash expectation for callers."""
    if from_state not in TRANSITIONS or to_state not in TRANSITIONS:
        raise ScheduleTransitionError(f"unknown state(s): {from_state} → {to_state}")
    if not can_transition(from_state, to_state):
        raise ScheduleTransitionError(f"illegal schedule transition {from_state} → {to_state}")

    if to_state in REVIEW_REQUIRED and not reviewer:
        raise ScheduleTransitionError(
            f"transition to '{to_state}' requires a recorded reviewer (§17)"
        )
    if to_state in REVIEW_REQUIRED and not version_hash:
        raise ScheduleTransitionError(
            f"transition to '{to_state}' must pin the approved version hash"
        )
    if to_state == "scheduled" and not version_hash:
        raise ScheduleTransitionError("scheduling requires the approved version hash")
    return version_hash or ""


def platform_metadata(
    platform: str,
    offer: dict[str, Any],
    evidence_urls: list[str],
    disclosure: dict[str, Any],
    correction_url: str | None = None,
    *,
    website_url: str | None = None,
    language: str = "en",
    variant: str = "default",
) -> dict[str, Any]:
    """Platform-specific copy with hard limits, disclosures, source links,
    website CTA, hashtags and a pinned comment (§6/§11/§17).

    `correction_url` adds the §11 correction/takedown permalink. `website_url`
    is the operator's tracked brand/offer link (UTM parameters are added).
    """
    eligibility = decode_mapping(offer.get("eligibility"))
    renewal = decode_mapping(offer.get("renewal"))
    # Never assert a generic "genuine end-to-end claim": an account-specific
    # walkthrough is not a promise that every viewer gets the same result (A13).
    normalized = {
        **offer,
        "eligibility": eligibility,
        "renewal": renewal,
    }
    return build_metadata(
        platform,
        normalized,
        evidence_urls=evidence_urls,
        disclosure=disclosure,
        correction_url=correction_url,
        website_url=website_url,
        language=language,
        variant=variant,
    )


def parse_publish_windows(value) -> list[str]:
    """Validate a publish-windows setting: list of unique HH:MM (00–23) local
    (Asia/Karachi) times. Returns the normalized list; raises ValueError."""
    if not isinstance(value, dict) or not isinstance(value.get("windows"), list):
        raise ValueError("publish_windows must be {\"windows\": [\"HH:MM\", …]}")
    out: list[str] = []
    for w in value["windows"]:
        parts = str(w).split(":")
        if len(parts) != 2 or not all(p.isdigit() and len(p) == 2 for p in parts):
            raise ValueError(f"invalid publish window {w!r} — want HH:MM")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"invalid publish window {w!r} — out of range")
        norm = f"{hour:02d}:{minute:02d}"
        if norm not in out:
            out.append(norm)
    if not out:
        raise ValueError("publish_windows needs at least one HH:MM time")
    return out


def default_publish_window(now: datetime | None = None,
                           windows: list[str] | None = None) -> str:
    """§17: "begin with a manageable cadence; never promise universal best
    hours." Picks the next occurrence among the operator's configured publish
    windows (settings.publish_windows, Asia/Karachi local = UTC+5) — falling
    back to the single 18:00 PKT default when unset."""
    now = now or datetime.now(timezone.utc)
    PKT = timezone(timedelta(hours=5))
    local = now.astimezone(PKT)

    times: list[tuple[int, int]] = []
    if windows:
        for w in windows:
            hh, mm = w.split(":")
            times.append((int(hh), int(mm)))
    else:
        times = [(18, 0)]

    candidates: list[datetime] = []
    for offset in (0, 1):  # today, then tomorrow
        day = (local + timedelta(days=offset)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        for hh, mm in times:
            c = day + timedelta(hours=hh, minutes=mm)
            if c > local:
                candidates.append(c)
    nxt = min(candidates).astimezone(timezone.utc)
    return nxt.isoformat()
