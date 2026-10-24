"""Structured field extraction (master plan §3).

The LLM is an extractor and comparator — NEVER the evidence source. Every
extracted field carries the exact evidence URL, an excerpt, and a confidence.

Two backends:
- rules: deterministic regex extraction, always available, fully testable.
- llm:   OpenAI-compatible chat endpoint when configured via env
         (VERIFY_LLM_BASE_URL, VERIFY_LLM_API_KEY, VERIFY_LLM_MODEL).
         Falls back to rules on any failure and records disagreement
         between the two as extraction conflicts.
"""

import json
import os
import re
from typing import Any, Optional

from document_sections import MAX_SECTION_CHARS, split_sections

# Shared cost client (packages/costing.py). The worker entrypoint puts the
# repo's packages/ dir on sys.path; the fallback keeps standalone test
# contexts working.
try:
    import costing
except ImportError:  # pragma: no cover — direct import in test contexts
    import sys as _sys
    _sys.path.insert(0, os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "packages")))
    import costing

# ---------------------------------------------------------------------------
# Rule-based extractor (deterministic baseline)

PROMO_RE = re.compile(
    r"(?:code|coupon|promo code)[:\s]+([A-Z0-9][A-Z0-9-]{3,24})\b"
    r"|\b([A-Z0-9][A-Z0-9-]{4,24})\b\s+(?:at checkout|promo code)"
)
PRICE_RE = re.compile(r"(?:(\$|USD\s?|PKR\s?|€)\s?)(\d[\d,]*(?:\.\d{1,2})?)")
EXPIRY_RE = re.compile(
    r"(?:ends?|expir(?:es?|y)|valid (?:until|through))\s*[:\-]?\s*"
    r"([A-Z][a-z]+ \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)
ELIGIBILITY_RE = re.compile(
    r"\b(students?|student id|new customers?|startups?|enrolled|faculty|verify.{0,20}enrollment)\b",
    re.IGNORECASE,
)
RENEWAL_RE = re.compile(
    r"(?:renew(?:s|al)?|auto-?renew\w*)[^.]{0,80}?(\$|USD\s?|PKR\s?)?\s?(\d[\d,]*(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# --- typed claims -----------------------------------------------------------
# These are classifications, not quoted text: the server verifies the quote
# carries the matching cue, so a wrong guess becomes `unknown`, not a claim.
BENEFIT_TYPE_RULES = (
    ("free", re.compile(
        r"\bfree (?:trial|tier|plan|month|credits?|access|of charge|for)\b"
        r"|\bat no cost\b|\bcomplimentary\b|\$\s?0\b",
        re.IGNORECASE,
    )),
    ("discounted", re.compile(
        r"\b\d{1,3}\s*%\s*off\b|\bdiscount(?:ed)?\b|\breduced (?:price|rate)\b",
        re.IGNORECASE,
    )),
    ("application_based", re.compile(
        r"\bapply\b|\bapplication\b|\bupon approval\b|\baward(?:ed)?\b",
        re.IGNORECASE,
    )),
)

WORLDWIDE_RE = re.compile(
    r"\b(?:available|open|valid|offered)\s+worldwide\b|\ball countries\b", re.IGNORECASE
)
REGION_LIST_RE = re.compile(
    r"\b(?:available|eligible|open|valid|offered)\s+(?:only\s+)?in\s+"
    r"((?:the\s+)?[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)?"
    r"(?:\s*(?:,|and|or)\s*(?:the\s+)?[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)?)*)"
)
EXCLUDED_REGION_RE = re.compile(
    r"\b(?:not available|unavailable|excluded?|except)\s+(?:in|for)\s+"
    r"((?:the\s+)?[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)?"
    r"(?:\s*(?:,|and|or)\s*(?:the\s+)?[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)?)*)"
)

AUTO_RENEW_NO_RE = re.compile(
    r"\b(?:does not|do not|will not|won't|no)\s+auto-?renew"
    r"|\bauto-?renew(?:al)?\s+is\s+(?:off|disabled)"
    r"|\bmanual renewal\b",
    re.IGNORECASE,
)
AUTO_RENEW_YES_RE = re.compile(
    r"\bauto-?renew(?:s|al|ing)?\b|\brenews automatically\b|\bautomatic renewal\b",
    re.IGNORECASE,
)

#: Renewal/initial cues used to label a price's basis.
_RENEWAL_CLAUSE_RE = re.compile(
    r"renew|after the (?:free|first|trial)|thereafter|afterwards|subsequent|auto-?renew",
    re.IGNORECASE,
)
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<!\d)\.(?!\d)|[!?\n]")

ALL_RULE_FIELDS = (
    "promo_code", "price", "expiry", "eligibility", "renewal",
    "benefit_type", "regions", "auto_renew",
)


def _excerpt(text: str, start: int, width: int = 90) -> str:
    lo, hi = max(0, start - 30), min(len(text), start + width)
    return text[lo:hi].strip()


def _sentence_at(text: str, position: int) -> str:
    """The sentence containing `position`; decimal points do not split."""
    low = 0
    high = len(text)
    for match in _SENTENCE_BOUNDARY_RE.finditer(text):
        if match.end() <= position:
            low = match.end()
        elif match.end() >= position and high == len(text):
            high = match.end()
            break
    return text[low:high].strip()


def _region_items(raw: str) -> list[str]:
    items = re.split(r"\s*(?:,|and|or)\s*", raw.strip())
    cleaned = []
    for item in items:
        item = re.sub(r"^the\s+", "", item.strip(), flags=re.IGNORECASE).strip()
        if item:
            cleaned.append(item)
    return cleaned


def price_basis(text: str, start: int) -> str:
    """Label a price as `initial` or `renewal` from its own sentence.

    A renewal price must never be presented as the price a viewer pays first,
    so this only says `initial` when no renewal clause shares the sentence.
    """
    return "renewal" if _RENEWAL_CLAUSE_RE.search(_sentence_at(text, start)) else "initial"


def extract_fields_rules(text: str, evidence_url: str) -> dict[str, dict[str, Any]]:
    """Deterministic extraction. Every field carries its evidence link (§18:
    every verified field links to evidence)."""
    fields: dict[str, dict[str, Any]] = {}

    def add(name: str, matched: str, start: int, confidence: float = 0.55,
            **extra: Any) -> None:
        fields[name] = {
            "value": matched,
            "evidence_url": evidence_url,
            "excerpt": _excerpt(text, start),
            "confidence": confidence,
            **extra,
        }

    match = PROMO_RE.search(text)
    if match:
        add("promo_code", next(g for g in match.groups() if g), match.start())

    match = PRICE_RE.search(text)
    if match:
        add("price", "".join(g for g in match.groups() if g), match.start(),
            basis=price_basis(text, match.start()))

    match = EXPIRY_RE.search(text)
    if match:
        add("expiry", match.group(1), match.start())

    match = ELIGIBILITY_RE.search(text)
    if match:
        add("eligibility", match.group(1), match.start())

    match = RENEWAL_RE.search(text)
    if match:
        add("renewal", match.group(0).strip()[:80], match.start())

    for benefit_type, pattern in BENEFIT_TYPE_RULES:
        match = pattern.search(text)
        if match:
            add("benefit_type", benefit_type, match.start(), confidence=0.5)
            break

    worldwide = WORLDWIDE_RE.search(text)
    regions = REGION_LIST_RE.search(text)
    if worldwide or regions:
        excluded = EXCLUDED_REGION_RE.search(text)
        start = worldwide.start() if worldwide else regions.start()
        value = "worldwide" if worldwide else ", ".join(_region_items(regions.group(1)))
        add(
            "regions", value, start, confidence=0.5,
            excluded_regions=_region_items(excluded.group(1)) if excluded else [],
        )

    # `no` is checked first: \"does not auto-renew\" also matches the yes rule.
    if AUTO_RENEW_NO_RE.search(text):
        add("auto_renew", "no", AUTO_RENEW_NO_RE.search(text).start(), confidence=0.5)
    elif AUTO_RENEW_YES_RE.search(text):
        add("auto_renew", "yes", AUTO_RENEW_YES_RE.search(text).start(), confidence=0.5)

    return fields


def is_complete(fields: dict[str, dict[str, Any]]) -> bool:
    """'Complete' means the offer's claimable core is pinned to evidence:
    a promo mechanism (code or price) AND eligibility context."""
    has_incentive = "promo_code" in fields or "price" in fields
    has_context = "eligibility" in fields or "expiry" in fields
    return has_incentive and has_context


# ---------------------------------------------------------------------------
# LLM extractor (optional; OpenAI-compatible endpoint)


def llm_configured() -> bool:
    return bool(os.environ.get("VERIFY_LLM_BASE_URL") and os.environ.get("VERIFY_LLM_API_KEY"))


def extract_fields_llm(
    text: str,
    evidence_url: str,
    *,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    cost: Optional[Any] = None,
    ref_offer_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Extract fields with an OpenAI-compatible LLM. Returns None on any
    failure — verification must never depend on the LLM being available.

    Cost engine (WP-F): with a `cost` client attached, the result is served
    from the shared `extract:{content-hash}:{model}` cache first (a
    re-verification of an unchanged page emits 0 tokens), the DAILY LLM
    BUDGET is checked BEFORE the call (denied → None — the deterministic
    rules path in extract() stays), and actual token usage is reported to
    the ledger afterwards.
    """
    import httpx

    base = (base_url or os.environ.get("VERIFY_LLM_BASE_URL", "")).rstrip("/")
    key = api_key or os.environ.get("VERIFY_LLM_API_KEY", "")
    model_id = model or os.environ.get("VERIFY_LLM_MODEL", "gpt-4o-mini")
    if not base or not key:
        return None

    if cost is not None:
        cache_key = costing.extraction_cache_key(model_id, text)
        cached = cost.cache_lookup("extract", cache_key)
        if cached is not None:
            cost.report("llm_extract", units=0, provider="openai-compatible",
                        model=model_id, unit_type="tokens",
                        ref_type="offer", ref_id=ref_offer_id,
                        meta={"cache_hit": True})
            return cached
        if not cost.budget_ok("llm_extract", provider="openai-compatible",
                              model=model_id, ref_type="offer",
                              ref_id=ref_offer_id):
            return None

    system = (
        "You extract structured offer data for a verification desk. "
        "Only report what the text literally supports. For each field give: "
        "value, evidence_url, excerpt (the exact supporting quote), confidence (0-1). "
        'Respond ONLY as JSON: {"fields": {...}, "conflicts": [...]}. '
        f"Use this evidence_url for every field: {evidence_url}. "
        f"Known field names: {', '.join(ALL_RULE_FIELDS)}. Quote must be verbatim. "
        "A price claim also needs basis=initial or basis=renewal; a regions claim "
        "may add excluded_regions. Never report an expiry you cannot quote."
    )
    body = {
        "model": model_id,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": text[:8000]}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=45,
        )
        resp.raise_for_status()
        payload = resp.json()
        content = payload["choices"][0]["message"]["content"]
        data = json.loads(content)
        if not isinstance(data.get("fields"), dict):
            return None
        if cost is not None:
            usage = payload.get("usage") or {}
            tokens_in = int(usage.get("prompt_tokens") or 0)
            tokens_out = int(usage.get("completion_tokens") or 0)
            cost.cache_store("extract", cache_key, data)
            cost.report("llm_extract", units=tokens_in + tokens_out,
                        provider="openai-compatible", model=model_id,
                        unit_type="tokens", ref_type="offer",
                        ref_id=ref_offer_id,
                        meta={"tokens_in": tokens_in, "tokens_out": tokens_out})
        return data
    except Exception:  # noqa: BLE001 — LLM failure must never block verification
        return None


def extract(
    text: str,
    evidence_url: str,
    *,
    cost: Optional[Any] = None,
    ref_offer_id: Optional[str] = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], Optional[str]]:
    """Combined extraction. Returns (fields, conflicts, model_used).

    When the LLM is configured and returns fields, rule-based and LLM results
    are compared; disagreements are recorded as conflicts for reviewer triage.
    Otherwise the deterministic rules result is used alone.
    """
    rules = extract_fields_rules(text, evidence_url)
    model_used: Optional[str] = None
    conflicts: list[dict[str, Any]] = []
    fields = rules

    if llm_configured():
        llm = extract_fields_llm(text, evidence_url, cost=cost,
                                 ref_offer_id=ref_offer_id)
        if llm is not None:
            model_used = os.environ.get("VERIFY_LLM_MODEL", "gpt-4o-mini")
            llm_fields = llm.get("fields", {})
            conflicts = _compare(rules, llm_fields)
            reported = llm.get("conflicts", [])
            if isinstance(reported, list) and all(isinstance(item, dict) for item in reported):
                conflicts.extend(reported)
            else:
                conflicts.append({"reason": "model returned malformed conflicts"})
            # LLM output wins but keeps rule fields the LLM missed; conflicts label it.
            merged = {**llm_fields, **{k: v for k, v in rules.items() if k not in llm_fields}}
            if merged:
                fields = merged

    return fields, conflicts, model_used


def extract_document(
    text: str,
    evidence_url: str,
    *,
    max_chars: int = MAX_SECTION_CHARS,
    cost: Optional[Any] = None,
    ref_offer_id: Optional[str] = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], Optional[str], int]:
    """Sectioned extraction over the whole document (WP01 slice 8).

    Every section is examined; the returned section count is what the API
    recomputes from the stored snapshot before it accepts the record. Sections
    that disagree about a value are kept as a conflict — the first value is
    retained for display, never the more attractive one, and a conflict blocks
    promotion for reviewer triage.
    """
    sections = split_sections(text, max_chars)
    fields: dict[str, dict[str, Any]] = {}
    first_seen: dict[str, int] = {}
    conflicts: list[dict[str, Any]] = []
    conflicted: set[str] = set()
    model_used: Optional[str] = None

    for section in sections:
        section_fields, section_conflicts, model = extract(
            section.text, evidence_url, cost=cost, ref_offer_id=ref_offer_id)
        model_used = model or model_used
        for name, field in section_fields.items():
            if name not in fields:
                fields[name] = field
                first_seen[name] = section.index
                continue
            same_value = (
                str(fields[name].get("value", "")).strip().casefold()
                == str(field.get("value", "")).strip().casefold()
            )
            if not same_value and name not in conflicted:
                conflicted.add(name)
                conflicts.append({
                    "field": name,
                    "reason": "document sections disagree",
                    "sections": [first_seen[name], section.index],
                })
            if same_value and name == "regions":
                # Union the exclusions so an earlier section cannot hide one.
                merged = {
                    *(fields[name].get("excluded_regions") or []),
                    *(field.get("excluded_regions") or []),
                }
                fields[name] = {
                    **fields[name],
                    "excluded_regions": sorted(merged),
                }
        for conflict in section_conflicts:
            conflicts.append({**conflict, "section": section.index})

    return fields, conflicts, model_used, len(sections)


def _compare(rules: dict, llm_fields: dict) -> list[dict[str, Any]]:
    conflicts = []
    for name in set(rules) | set(llm_fields):
        r_value = (rules.get(name) or {}).get("value")
        l_value = (llm_fields.get(name) or {}).get("value")
        if r_value and l_value and str(r_value).strip().lower() != str(l_value).strip().lower():
            conflicts.append({"field": name, "rules": r_value, "llm": l_value})
    return conflicts
