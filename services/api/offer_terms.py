"""Offer-type terms contract (master plan §6, steps 5-9).

A verified offer needs more than a price and the word "students". The server
builds a *fact pack*: one explicit status per claim field.

    supported        the claim is literally present in the official snapshot
                     and nothing in the quoted terms contradicts it
    contradicted     the quoted official terms state the opposite
    unknown          the inspected terms do not establish the claim
    not_applicable   the offer type does not require this field

`unknown` and `contradicted` are not cosmetic labels. A required field that is
not `supported` blocks automatic verification and forces human review. An
unknown fact never becomes "free", "worldwide", "open eligibility", "unlimited"
or "never expires" (§6 step 7), and a conflict is never auto-corrected into the
more attractive claim (§6 step 9).

This module is pure: it decides from the submitted field, its quote and the
offer type. It never trusts a caller-supplied `complete` flag, a model's
confidence, or the model's own opinion of its answer.

Semantic detection is deliberately conservative and abstains when it cannot
tell. A page containing a number and "students" is not an offer (§6 step 6).
"""

from __future__ import annotations

import re
from typing import Any, Final, Mapping

SUPPORTED: Final = "supported"
CONTRADICTED: Final = "contradicted"
UNKNOWN: Final = "unknown"
NOT_APPLICABLE: Final = "not_applicable"

#: Every claim field the contract can speak about. The order is stable so the
#: fact pack is deterministic.
CLAIM_FIELDS: Final[tuple[str, ...]] = (
    "promo_code", "price", "value", "benefit_type", "eligibility",
    "regions", "expiry", "renewal", "auto_renew",
)

#: A claim that describes what the viewer receives.
INCENTIVE_FIELDS: Final[tuple[str, ...]] = ("promo_code", "price", "value")
#: A claim that describes who may receive it and for how long.
CONTEXT_FIELDS: Final[tuple[str, ...]] = ("eligibility", "expiry")

#: Offer types with a published terms contract, mapped to the fields that must
#: be `supported` before automatic release (§6 "Required fact-pack gates by
#: format"). An offer type that is absent here has no agreed contract yet and
#: falls back to the baseline core below — recorded as such in the fact pack.
OFFER_TYPE_REQUIREMENTS: Final[dict[str, tuple[str, ...]]] = {
    # Free/API credit offer: benefit type, audience, deadline, billing terms.
    "free_trial": ("value", "benefit_type", "eligibility", "expiry", "renewal", "auto_renew"),
    "credits": ("value", "benefit_type", "eligibility", "expiry"),
    # Student/startup program: application-based award conditions.
    "student_perk": ("value", "benefit_type", "eligibility", "expiry"),
    # Open-weight model: artifact plus licence/usage conditions.
    "model_access": ("value", "benefit_type", "eligibility"),
    # Domain discount: initial and renewal cost, auto-renew status.
    "domain_discount": ("price", "eligibility", "renewal", "auto_renew"),
    # Tool/model release explainer: version, date, capability limits.
    "release_explainer": ("value", "eligibility", "expiry"),
    # Real claim walkthrough: full offer checks before filming.
    "walkthrough": ("value", "eligibility", "expiry", "renewal"),
}

#: A contradiction must sit in the same sentence as the quoted value, so a
#: phrase about shipping does not contradict the plan's price.
_SENTENCE_BOUNDARY_RE: Final = re.compile(r"(?<!\d)\.(?!\d)|[!?\n]")

RENEWAL_CUES: Final[tuple[str, ...]] = (
    "renew", "after the free period", "subsequent", "thereafter",
    "each year after", "auto-renew", "automatically renew", "automatic renewal",
)

AUTO_RENEW_YES_CUES: Final[tuple[str, ...]] = (
    "auto-renew", "auto renew", "automatically renew", "automatic renewal",
    "renews automatically", "renewal is on",
)

AUTO_RENEW_NO_CUES: Final[tuple[str, ...]] = (
    "no auto-renew", "no auto renew", "not auto-renew", "auto-renew is off",
    "auto renewal is off", "does not auto-renew", "renewal is disabled",
    "manual renewal", "does not renew automatically",
)

APPLICATION_CUES: Final[tuple[str, ...]] = (
    "application", "apply", "approval", "approved", "award", "applicant",
)

DISCOUNT_CUES: Final[tuple[str, ...]] = (
    "discount", "% off", "percent off", "reduced", "save ", "lowered", "off the",
)

#: A free *benefit*, not an incidental free extra such as "free shipping".
FREE_BENEFIT_CUES: Final[tuple[str, ...]] = (
    "free trial", "free of charge", "for free", "free access", "free plan",
    "free month", "free credit", "free credits", "free domain", "no charge",
    "at no cost", "complimentary", "$0",
)

EXCLUSION_CUES: Final[tuple[str, ...]] = (
    "excludes", "excluding", "except in", "except for", "not available in",
    "unavailable in", "not offered in", "does not apply in", "is not available in",
)

#: Claims whose value is a normalized classification, not text quoted from the
#: official page. "yes" and "free" are the server's words, so literal-support
#: checking does not apply to them; their quote must carry the matching cue.
CLASSIFIED_CLAIMS: Final[frozenset[str]] = frozenset({"benefit_type", "auto_renew"})

#: Claims whose value is a list. Every listed item must appear in the quote.
LIST_CLAIMS: Final[frozenset[str]] = frozenset({"regions"})

#: Phrases in the quoted official terms that contradict a positive claim.
CONTRADICTION_CUES: Final[dict[str, tuple[str, ...]]] = {
    "promo_code": (
        "no promo code", "no discount code", "no code", "without a code",
        "not redeemable", "cannot be redeemed", "code is not valid",
        "code not valid", "codes are not accepted", "promo code is void",
    ),
    "price": (
        "not free", "not free of charge", "no longer free", "trial has ended",
        "costs extra", "additional fee", "not free during",
    ),
    "value": (
        "not free", "not free of charge", "no credit", "no credits",
        "not available", "offer has ended", "no longer available",
    ),
    "benefit_type": (
        "not free", "no longer free", "paid only", "requires approval",
        "not a free offer",
    ),
    "expiry": (
        "offer has ended", "has expired", "expired", "no longer available",
        "is closed", "offer closed", "ended",
    ),
    "eligibility": (
        "not eligible", "are not eligible", "is not eligible", "ineligible",
        "not open to", "does not apply to students", "not available to students",
        "not open to students", "only for existing customers",
    ),
    "renewal": (
        "does not renew", "no renewal", "will not renew", "non-renewing",
        "non renewing",
    ),
    "auto_renew": (
        "does not auto-renew", "no auto-renew", "auto-renewal is off",
        "auto renewal is off", "renewal is disabled",
    ),
}

_DATE_RE: Final = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b",
    re.IGNORECASE,
)

#: A deadline that is not a date. "No expiry stated" is not "never expires".
_NON_SPECIFIC_DEADLINE_RE: Final = re.compile(
    r"no expiry|no expiration|never expires|never ends|ongoing|tbd|to be announced"
    r"|end of year|until further notice|not stated",
    re.IGNORECASE,
)

_WORLDWIDE_CLAIMS: Final[tuple[str, ...]] = (
    "worldwide", "all countries", "everywhere", "global", "any country",
    "in every country",
)


def _value_span(value: str, excerpt: str, *, list_claim: bool = False) -> tuple[int, int] | None:
    """Locate the value inside the quote, tolerating case and whitespace.

    Mirrors the literal-support rule in `verification_checks` so the fact pack
    and the server gate never disagree about what is quoted. A list claim
    matches when every listed item is present.
    """
    if not value:
        return None
    if list_claim:
        parts = [part.strip() for part in re.split(r"[,;]", value) if part.strip()]
        if not parts:
            return None
        spans = []
        for part in parts:
            span = _single_span(part, excerpt)
            if span is None:
                return None
            spans.append(span)
        return (min(span[0] for span in spans), max(span[1] for span in spans))
    return _single_span(value, excerpt)


def _single_span(value: str, excerpt: str) -> tuple[int, int] | None:
    if not value:
        return None
    pattern = r"\s*".join(re.escape(part) for part in value.split())
    match = re.search(r"(?<!\w)" + pattern + r"(?!\w|[.,]\d)", excerpt, flags=re.IGNORECASE)
    return (match.start(), match.end()) if match else None


def _has_cue(text: str, cues: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for cue in cues:
        if cue in lowered:
            return cue
    return None


def _sentence_window(excerpt: str, start: int, end: int) -> str:
    """The sentence containing the quoted value, not the whole page.

    A contradicting phrase in an unrelated sentence does not contradict this
    claim; a short excerpt keeps everything in one sentence. Decimal points
    are not sentence boundaries.
    """
    boundaries = [match.end() for match in _SENTENCE_BOUNDARY_RE.finditer(excerpt)]
    low = 0
    for boundary in boundaries:
        if boundary <= start:
            low = boundary
        else:
            break
    high = len(excerpt)
    for boundary in boundaries:
        if boundary >= end:
            high = boundary
            break
    return excerpt[low:high].lower()


def _contradicting_cue(name: str, value: str, excerpt: str) -> str | None:
    """A contradicting phrase must sit in the quote's own sentence.

    A classified claim ("yes", "free") has no quoted token of its own, so its
    contradiction cues are read from the whole quote.
    """
    span = _value_span(value, excerpt, list_claim=name in LIST_CLAIMS)
    if span is None:
        window = excerpt.lower()
    else:
        window = _sentence_window(excerpt, *span)
    for cue in CONTRADICTION_CUES.get(name, ()):
        if cue in window:
            return cue
    return None


def _classify_expiry(value: str, excerpt: str) -> dict[str, Any]:
    if _DATE_RE.search(value):
        return {"status": SUPPORTED, "reason": "a specific deadline is stated in the quoted terms"}
    if _NON_SPECIFIC_DEADLINE_RE.search(value):
        return {
            "status": UNKNOWN,
            "reason": ("no expiry stated in the inspected terms — this is not proof "
                       "that the offer never expires"),
        }
    return {"status": UNKNOWN, "reason": "the deadline is not a specific date"}


def _classify_price(value: str, excerpt: str, field: Mapping[str, Any]) -> dict[str, Any]:
    """Separate the initial price from the renewal price (§6 step 5)."""
    basis = str(field.get("basis") or "").strip().lower()
    quoted_renewal = _has_cue(excerpt, RENEWAL_CUES)
    if basis not in ("initial", "renewal"):
        if quoted_renewal:
            return {
                "status": UNKNOWN,
                "reason": ("the quote mixes initial and renewal terms — the price "
                           "basis is not stated"),
            }
        return {
            "status": SUPPORTED,
            "reason": "the price is stated outside any renewal clause",
            "basis": "initial",
        }
    if basis == "initial" and quoted_renewal:
        return {
            "status": CONTRADICTED,
            "reason": "the quoted figure is the renewal price, not the initial price",
            "basis": "initial",
        }
    return {
        "status": SUPPORTED,
        "reason": f"the {basis} price is stated in the quoted terms",
        "basis": basis,
    }


def _classify_renewal(value: str, excerpt: str) -> dict[str, Any]:
    if not _has_cue(excerpt, RENEWAL_CUES):
        return {
            "status": UNKNOWN,
            "reason": "the quoted terms do not state a renewal price",
        }
    return {"status": SUPPORTED, "reason": "a renewal price is stated in the quoted terms"}


def _classify_auto_renew(value: str, excerpt: str) -> dict[str, Any]:
    normalised = value.strip().lower()
    if normalised == "yes":
        if _has_cue(excerpt, AUTO_RENEW_YES_CUES):
            return {"status": SUPPORTED, "reason": "auto-renewal is stated in the quoted terms"}
        return {
            "status": UNKNOWN,
            "reason": "auto-renewal is claimed but the quoted terms do not state it",
        }
    if normalised == "no":
        if _has_cue(excerpt, AUTO_RENEW_NO_CUES):
            return {
                "status": SUPPORTED,
                "reason": "the quoted terms state that renewal is not automatic",
            }
        return {
            "status": UNKNOWN,
            "reason": "the absence of auto-renewal is not stated in the quoted terms",
        }
    return {"status": UNKNOWN, "reason": "auto-renewal must be yes or no"}


def _classify_benefit_type(value: str, excerpt: str) -> dict[str, Any]:
    normalised = value.strip().lower()
    if normalised == "free":
        if not _has_cue(excerpt, FREE_BENEFIT_CUES):
            return {
                "status": UNKNOWN,
                "reason": ("the word 'free' appears but the quoted terms do not "
                           "describe a free benefit"),
            }
        return {"status": SUPPORTED, "reason": "the quoted terms describe a free benefit"}
    if normalised == "discounted":
        if _has_cue(excerpt, DISCOUNT_CUES):
            return {"status": SUPPORTED, "reason": "the quoted terms state a discount"}
        return {
            "status": UNKNOWN,
            "reason": "a discount is claimed but the quoted terms do not state one",
        }
    if normalised == "application_based":
        if _has_cue(excerpt, APPLICATION_CUES):
            return {
                "status": SUPPORTED,
                "reason": "the quoted terms require an application or approval",
            }
        return {
            "status": UNKNOWN,
            "reason": ("an application-based award is claimed but the quoted terms "
                       "do not say so"),
        }
    return {
        "status": UNKNOWN,
        "reason": "benefit type must be free, discounted or application_based",
    }


def _classify_regions(value: str, excerpt: str, field: Mapping[str, Any]) -> dict[str, Any]:
    excluded = [str(item).strip() for item in (field.get("excluded_regions") or []) if str(item).strip()]
    normalised = value.strip().lower()
    claims_worldwide = any(normalised == claim or normalised.startswith(claim + ",")
                           for claim in _WORLDWIDE_CLAIMS)
    span = _value_span(value, excerpt, list_claim=True)
    window = _sentence_window(excerpt, *span) if span else excerpt.lower()
    exclusion_cue = _has_cue(window, EXCLUSION_CUES)
    if claims_worldwide and (excluded or exclusion_cue):
        return {
            "status": CONTRADICTED,
            "reason": "the offer is not worldwide — the quoted terms exclude some regions",
            "excluded_regions": excluded,
        }
    if exclusion_cue and not excluded:
        return {
            "status": UNKNOWN,
            "reason": ("the quoted terms exclude a region that this claim does not "
                       "record"),
            "excluded_regions": excluded,
        }
    if claims_worldwide:
        return {
            "status": SUPPORTED,
            "reason": "the quoted terms state worldwide availability",
            "excluded_regions": excluded,
        }
    return {
        "status": SUPPORTED,
        "reason": "the eligible regions are stated in the quoted terms",
        "excluded_regions": excluded,
    }


def _as_mapping(field: Any) -> Mapping[str, Any]:
    """Accept a plain mapping or a pydantic model for one claim field."""
    if isinstance(field, Mapping):
        return field
    dump = getattr(field, "model_dump", None)
    if callable(dump):
        return dump()
    return {}


def classify_field(name: str, field: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Derive one field's status from its value, quote and claim type.

    The caller decides whether the quote is established against the stored
    snapshot; `established=False` forces `unknown` regardless of what the
    quote appears to say.
    """
    data = _as_mapping(field)
    value = str(data.get("value") or "").strip()
    excerpt = str(data.get("excerpt") or "").strip()
    if not value or not excerpt:
        return {"status": UNKNOWN, "reason": "the field has no value or no quote"}
    if name not in CLASSIFIED_CLAIMS:
        if _value_span(value, excerpt, list_claim=name in LIST_CLAIMS) is None:
            return {
                "status": UNKNOWN,
                "reason": "the value is not literally present in the quoted snapshot text",
            }
    cue = _contradicting_cue(name, value, excerpt)
    if cue:
        return {
            "status": CONTRADICTED,
            "reason": f"the quoted official terms contradict this claim ({cue!r})",
        }
    if name == "expiry":
        return _classify_expiry(value, excerpt)
    if name == "price":
        return _classify_price(value, excerpt, data)
    if name == "renewal":
        return _classify_renewal(value, excerpt)
    if name == "auto_renew":
        return _classify_auto_renew(value, excerpt)
    if name == "benefit_type":
        return _classify_benefit_type(value, excerpt)
    if name == "regions":
        return _classify_regions(value, excerpt, data)
    return {
        "status": SUPPORTED,
        "reason": "the value is literally present in the quoted snapshot text",
    }


def required_fields(offer_type: str) -> tuple[str, ...]:
    """The published contract for this offer type, if there is one."""
    return OFFER_TYPE_REQUIREMENTS.get((offer_type or "").strip().lower(), ())


def build_fact_pack(
    offer_type: str,
    fields: Mapping[str, Mapping[str, Any]],
    established: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the per-field fact pack for one extraction proposal.

    `established` names the fields whose quote and value were proven against
    the stored, hash-checked snapshot. Any field outside that set is `unknown`
    — the server never treats an unproven quote as support.
    """
    proven = established if established is not None else set(fields)
    required = set(required_fields(offer_type))
    pack: dict[str, dict[str, Any]] = {}
    for name in CLAIM_FIELDS:
        field = fields.get(name)
        if field is None:
            if name in required:
                pack[name] = {
                    "status": UNKNOWN,
                    "reason": "required for this offer type but not established by the extraction",
                    "required": True,
                }
            else:
                pack[name] = {
                    "status": NOT_APPLICABLE,
                    "reason": "not required for this offer type",
                    "required": False,
                }
            continue
        if name not in proven:
            pack[name] = {
                "status": UNKNOWN,
                "reason": "the quote and value are not proven against the stored snapshot",
                "required": name in required,
            }
            continue
        entry = classify_field(name, field)
        entry["required"] = name in required
        pack[name] = entry
    return pack


def fact_pack_problems(offer_type: str, pack: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Blocking problems for this offer type, derived from the fact pack.

    A claim the official terms contradict is always a problem: a conflict is
    never auto-corrected into the more attractive claim (§6 step 9), so the
    offer is quarantined for review instead of being published.
    """
    problems: list[str] = []
    required = required_fields(offer_type)
    for name in CLAIM_FIELDS:
        entry = pack.get(name) or {}
        if entry.get("status") == CONTRADICTED:
            reason = entry.get("reason", "the quoted terms state the opposite")
            problems.append(f"{name}: contradicted — {reason}")

    if required:
        for name in required:
            entry = pack.get(name) or {}
            status = entry.get("status", UNKNOWN)
            if status in (SUPPORTED, CONTRADICTED):
                continue
            reason = entry.get("reason", "not established by the quoted terms")
            problems.append(f"{name}: {status} — {reason}")
        return problems

    # No published contract for this offer type yet: fall back to the baseline
    # core, which is deliberately weaker than a type-specific checklist.
    if not any((pack.get(name) or {}).get("status") == SUPPORTED for name in INCENTIVE_FIELDS):
        problems.append(
            "no incentive (promo_code, price or value) is established by the quoted terms"
        )
    if not any((pack.get(name) or {}).get("status") == SUPPORTED for name in CONTEXT_FIELDS):
        problems.append(
            "no eligibility or expiry context is established by the quoted terms"
        )
    return problems


def derive_completeness(
    offer_type: str,
    pack: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    """Server-derived completeness for this offer type.

    Returns `(complete, problems)`. `complete` is False whenever any required
    claim is unknown or contradicted, so missing critical facts block
    automatic verification instead of becoming marketing copy.
    """
    problems = fact_pack_problems(offer_type, pack)
    return (not problems), problems
