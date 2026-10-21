"""Pure, conservative evidence checks shared by ingestion and promotion gates.

Literal support is necessary, not sufficient, for semantic offer verification.
Type-specific terms/eligibility rules and fresh fetch provenance remain WP01 work.
"""

import hashlib
import re
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

from schemas import ExtractionIn


def domain_matches(url: str, domains: Sequence[str]) -> bool:
    """Match a registered hostname exactly or at a subdomain boundary."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        host = (parsed.hostname or "").rstrip(".").encode("idna").decode().lower()
        for domain in domains:
            domain = domain.strip().rstrip(".").encode("idna").decode().lower()
            if not domain or any(c in domain for c in "/:@?# "):
                continue
            if host == domain or host.endswith("." + domain):
                return True
    except (ValueError, UnicodeError):
        return False
    return False


def extraction_problems(extraction: ExtractionIn, evidence: Sequence[Mapping]) -> list[str]:
    """Check literal support, not semantic truth or current live applicability.

    The DB caller filters current active Tier-A ownership and offer membership.
    Quotes must be verbatim; values may vary only in case/whitespace. This
    deliberately abstains on paraphrases instead of certifying an invented fact.
    """
    problems = []
    if extraction.conflicts:
        problems.append("unresolved extraction conflicts require review")
    by_id = {str(row["id"]): row for row in evidence if row["official"] and row["domain_ok"]}
    for name, field in extraction.fields.items():
        row = by_id.get(str(field.evidence_id))
        if row is None or row["url"] != str(field.evidence_url):
            problems.append(f"{name}: requires official evidence belonging to this offer and exact URL")
            continue
        text = row["captured_content"]
        if not text or hashlib.sha256(text.encode("utf-8")).hexdigest() != row["content_hash"]:
            problems.append(f"{name}: snapshot unavailable or hash mismatch; recapture required")
            continue
        if field.excerpt not in text:
            problems.append(f"{name}: quote is not in the captured snapshot")
        literal = r"\s*".join(re.escape(part) for part in field.value.split())
        if not re.search(r"(?<!\w)" + literal + r"(?!\w|[.,]\d)", field.excerpt, flags=re.IGNORECASE):
            problems.append(f"{name}: value is not literally supported by its quote")
    return problems


def core_complete(extraction: ExtractionIn) -> bool:
    """Baseline claim core only; never a replacement for offer-type terms checks."""
    names = extraction.fields.keys()
    return bool({"promo_code", "price", "value"} & names and {"eligibility", "expiry"} & names)
