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

ALL_RULE_FIELDS = ("promo_code", "price", "expiry", "eligibility", "renewal")


def _excerpt(text: str, start: int, width: int = 90) -> str:
    lo, hi = max(0, start - 30), min(len(text), start + width)
    return text[lo:hi].strip()


def extract_fields_rules(text: str, evidence_url: str) -> dict[str, dict[str, Any]]:
    """Deterministic extraction. Every field carries its evidence link (§18:
    every verified field links to evidence)."""
    fields: dict[str, dict[str, Any]] = {}

    def add(name: str, matched: str, start: int, confidence: float = 0.55) -> None:
        fields[name] = {
            "value": matched,
            "evidence_url": evidence_url,
            "excerpt": _excerpt(text, start),
            "confidence": confidence,
        }

    match = PROMO_RE.search(text)
    if match:
        add("promo_code", next(g for g in match.groups() if g), match.start())

    match = PRICE_RE.search(text)
    if match:
        add("price", "".join(g for g in match.groups() if g), match.start())

    match = EXPIRY_RE.search(text)
    if match:
        add("expiry", match.group(1), match.start())

    match = ELIGIBILITY_RE.search(text)
    if match:
        add("eligibility", match.group(1), match.start())

    match = RENEWAL_RE.search(text)
    if match:
        add("renewal", match.group(0).strip()[:80], match.start())

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
) -> Optional[dict[str, Any]]:
    """Extract fields with an OpenAI-compatible LLM. Returns None on any
    failure — verification must never depend on the LLM being available."""
    import httpx

    base = (base_url or os.environ.get("VERIFY_LLM_BASE_URL", "")).rstrip("/")
    key = api_key or os.environ.get("VERIFY_LLM_API_KEY", "")
    model_id = model or os.environ.get("VERIFY_LLM_MODEL", "gpt-4o-mini")
    if not base or not key:
        return None

    system = (
        "You extract structured offer data for a verification desk. "
        "Only report what the text literally supports. For each field give: "
        "value, evidence_url, excerpt (the exact supporting quote), confidence (0-1). "
        'Respond ONLY as JSON: {"fields": {...}, "conflicts": [...]}. '
        f"Use this evidence_url for every field: {evidence_url}. "
        f"Known field names: {', '.join(ALL_RULE_FIELDS)}. Quote must be verbatim."
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
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        if not isinstance(data.get("fields"), dict):
            return None
        return data
    except Exception:  # noqa: BLE001 — LLM failure must never block verification
        return None


def extract(
    text: str,
    evidence_url: str,
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
        llm = extract_fields_llm(text, evidence_url)
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


def _compare(rules: dict, llm_fields: dict) -> list[dict[str, Any]]:
    conflicts = []
    for name in set(rules) | set(llm_fields):
        r_value = (rules.get(name) or {}).get("value")
        l_value = (llm_fields.get(name) or {}).get("value")
        if r_value and l_value and str(r_value).strip().lower() != str(l_value).strip().lower():
            conflicts.append({"field": name, "rules": r_value, "llm": l_value})
    return conflicts
