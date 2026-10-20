"""Offer lifecycle state machine — server-side authority.

Mirrors packages/offer-schema (TypeScript) so the API can enforce the rules
even when callers misbehave. Master plan §3:

    Candidate → Evidence needed → Verified → Approved for video → Published
                                                  ↘ Expired/Corrected

HARD RULE: video generation and scheduling are blocked from Candidate or
Evidence needed. Verified requires official, provider-domain-checked evidence.
"""

from typing import Final

OFFER_STATES: Final = (
    "candidate",
    "evidence_needed",
    "verified",
    "approved_for_video",
    "published",
    "expired",
    "corrected",
)

OfferState = str  # one of OFFER_STATES; kept str for asyncpg passthrough

TRANSITIONS: Final[dict[str, tuple[str, ...]]] = {
    "candidate": ("evidence_needed", "expired"),
    "evidence_needed": ("candidate", "verified", "expired"),
    "verified": ("approved_for_video", "evidence_needed", "expired", "corrected"),
    "approved_for_video": ("published", "verified", "expired", "corrected"),
    "published": ("expired", "corrected"),
    "expired": ("evidence_needed",),
    "corrected": ("evidence_needed", "verified"),
}

# States from which video/schedule artifacts may be produced (§3: blocked from
# Candidate or Evidence needed).
VIDEO_ALLOWED_STATES: Final = frozenset({"verified", "approved_for_video", "published"})

# Human review is mandatory for these targets (recorded with user + time).
REVIEW_REQUIRED_TARGETS: Final = frozenset({"approved_for_video", "published"})


def can_transition(from_state: str, to_state: str) -> bool:
    return to_state in TRANSITIONS.get(from_state, ())


def can_generate_video(state: str) -> bool:
    return state in VIDEO_ALLOWED_STATES


def requires_review(to_state: str) -> bool:
    return to_state in REVIEW_REQUIRED_TARGETS


class TransitionError(ValueError):
    """Raised when a requested state change is illegal or ungated."""
