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

PLATFORMS: Final[tuple[str, ...]] = ("youtube", "facebook", "instagram", "tiktok")

# Plan §6/§17: official-API constraints to respect; limits drive metadata.
PLATFORM_LIMITS: Final[dict[str, dict[str, int]]] = {
    "youtube": {"title": 100, "caption": 5000, "tags": 500},
    "facebook": {"title": 120, "caption": 5000, "tags": 0},
    "instagram": {"title": 0, "caption": 2200, "tags": 30},   # professional account API
    "tiktok": {"title": 0, "caption": 2200, "tags": 0},       # Content Posting API
}

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


def platform_metadata(platform: str, offer: dict[str, Any], evidence_urls: list[str],
                      disclosure: dict[str, Any], correction_url: str | None = None) -> dict[str, str]:
    """Platform-specific copy template (§6) with hard limits, disclosures, and
    source links in the description (§11). `correction_url` (v0.17) adds the
    §11 correction/takedown permalink — set MTK_PUBLIC_BASE_URL in deployments
    with a reachable dashboard."""
    if platform not in PLATFORMS:
        raise ValueError(f"unsupported platform '{platform}' — known: {', '.join(PLATFORMS)}")

    limits = PLATFORM_LIMITS[platform]
    provider = offer.get("provider", "")
    title_base = f"{offer.get('title', 'Offer walkthrough')} — real claim walkthrough"
    title = title_base[: limits["title"]] if limits["title"] else ""

    eligibility = decode_mapping(offer.get("eligibility"))
    audience = []
    if eligibility.get("countries"):
        audience.append(f"Region: {', '.join(eligibility['countries'])}")
    if eligibility.get("studentStatus"):
        audience.append("students (verification required)")
    if eligibility.get("newCustomerOnly"):
        audience.append("new customers only")

    renewal = decode_mapping(offer.get("renewal"))
    lines: list[str] = [
        f"Genuine end-to-end claim of {offer.get('title', 'this offer')} by {provider}.",
        " · ".join(audience) if audience else "Check official terms for current eligibility.",
    ]
    if renewal.get("regularPrice"):
        lines.append(
            f"After the free period this renews at {renewal['regularPrice']}"
            f"{' (auto-renew)' if renewal.get('autoRenew') else ''}."
        )
    if disclosure.get("synthetic_narration"):
        lines.append("Narration is AI-generated (disclosed per platform policy).")
    if correction_url:
        lines.append(f"Corrections & updates: {correction_url}")
    if evidence_urls:
        lines.append("Sources & terms (may change):")
        lines.extend(f"- {u}" for u in evidence_urls[:3])

    caption = "\n".join(lines)
    if len(caption) > limits["caption"]:
        caption = caption[: limits["caption"] - 1].rstrip() + "…"

    return {"platform": platform, "title": title, "caption": caption,
            "privacy_default": "private"}


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
