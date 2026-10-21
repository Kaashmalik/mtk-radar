"""Pure, conservative evidence checks shared by ingestion and promotion gates.

Literal support is necessary, not sufficient, for semantic offer verification.
Type-specific terms/eligibility rules and fresh fetch provenance remain WP01 work.
"""

import hashlib
import re
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

from schemas import ExtractionIn
from offer_terms import CLASSIFIED_CLAIMS, LIST_CLAIMS


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


def field_problems(extraction: ExtractionIn, evidence: Sequence[Mapping]) -> dict[str, list[str]]:
    """Per-field literal-support problems, keyed by claim field name.

    The DB caller filters current active Tier-A ownership and offer membership.
    Quotes must be verbatim; values may vary only in case/whitespace. This
    deliberately abstains on paraphrases instead of certifying an invented fact.
    A field with no problems here is *established*; anything else must not be
    treated as support by the offer-type fact pack.
    """
    problems: dict[str, list[str]] = {}
    if extraction.conflicts:
        problems["__conflicts__"] = ["unresolved extraction conflicts require review"]
    by_id = {str(row["id"]): row for row in evidence if row["official"] and row["domain_ok"]}
    for name, field in extraction.fields.items():
        issues: list[str] = []
        row = by_id.get(str(field.evidence_id))
        if row is None or row["url"] != str(field.evidence_url):
            issues.append(f"{name}: requires official evidence belonging to this offer and exact URL")
        else:
            text = row["captured_content"]
            if not text or hashlib.sha256(text.encode("utf-8")).hexdigest() != row["content_hash"]:
                issues.append(f"{name}: snapshot unavailable or hash mismatch; recapture required")
            elif field.excerpt not in text:
                issues.append(f"{name}: quote is not in the captured snapshot")
            elif not literal_supported(name, field.value, field.excerpt):
                issues.append(f"{name}: value is not literally supported by its quote")
        if issues:
            problems[name] = issues
    return problems


def literal_supported(name: str, value: str, excerpt: str) -> bool:
    """Is this claim's value literally present in its quote?

    A classified claim ("yes", "free") is the server's own normalization, not
    text from the page, so its quote is checked by the offer-type contract
    instead. A list claim holds when every listed item is quoted.
    """
    if name in CLASSIFIED_CLAIMS:
        return True
    if name in LIST_CLAIMS:
        parts = [part.strip() for part in re.split(r"[,;]", value) if part.strip()]
        return bool(parts) and all(
            _quoted(part, excerpt) for part in parts
        )
    return _quoted(value, excerpt)


def _quoted(value: str, excerpt: str) -> bool:
    literal = r"\s*".join(re.escape(part) for part in value.split())
    if not literal:
        return False
    return bool(re.search(r"(?<!\w)" + literal + r"(?!\w|[.,]\d)", excerpt, flags=re.IGNORECASE))


def extraction_problems(extraction: ExtractionIn, evidence: Sequence[Mapping]) -> list[str]:
    """Flat list of literal-support problems across every submitted field."""
    problems: list[str] = []
    for issues in field_problems(extraction, evidence).values():
        problems.extend(issues)
    return problems


def established_fields(extraction: ExtractionIn, evidence: Sequence[Mapping]) -> set[str]:
    """Names of the fields whose quote and value are proven against the snapshot.

    `field_problems` only records fields that HAVE a problem, so the
    established set is derived from the submitted fields, not from that map.
    """
    problems = field_problems(extraction, evidence)
    return {name for name in extraction.fields if not problems.get(name)}
