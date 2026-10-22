"""Trend radar scoring (v0.27).

Topic discovery used to be a feed monitor: it could tell you that a page
changed, never whether the change was worth filming. This module turns a raw
inbox item into a transparent, explainable signal:

    demand          is there a real search/click incentive?
    freshness       is the offer new enough to be useful?
    feasibility     can we verify and actually claim it?
    competition_gap how crowded is the same story already?
    audience_fit    does it fit the channels and regions we serve?
    monetization    is there a credible video angle / value to show?

The score is deliberately deterministic and evidence-free of any LLM call:
every number can be recomputed from the item, and `score_reason` explains it
to an operator. Discovery proposes; verification still proves.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Final, Iterable

# Keywords that historically correlate with a claimable, video-worthy offer.
_HIGH_INTENT: Final[dict[str, int]] = {
    "free": 12, "trial": 10, "credit": 12, "credits": 12, "coupon": 8,
    "promo": 8, "student": 12, "education": 10, "startup": 9, "founder": 7,
    "domain": 8, "hosting": 8, "cloud": 8, "api": 7, "ai": 6, "gpu": 9,
    "voucher": 8, "giveaway": 7, "lifetime": 9, "deal": 7, "discount": 6,
    "verification": 6, "eligibility": 6, "claim": 8, "redeem": 8,
    "scholarship": 9, "license": 6, "subscription": 6, "workspace": 7,
}

_AUDIENCE_CATEGORIES: Final[dict[str, int]] = {
    "student_programs": 18, "developer_tools": 14, "model_hubs": 12,
    "cloud_platforms": 14, "domains_hosting": 12, "ai_tools": 12,
    "education": 14, "startup_perks": 13, "saved_links": 7,
}

_SOURCE_TIER: Final[dict[str, int]] = {
    "A_provider_owned": 18, "B_discovery_lead": 7, "C_excluded": 0,
}

_FRIENDLY_COUNTRIES: Final[frozenset[str]] = frozenset(
    {"PK", "US", "GB", "UK", "CA", "AU", "DE", "AE", "SA", "IN", "BD"}
)

_GENERIC_TITLE_WORDS: Final[frozenset[str]] = frozenset(
    {"the", "a", "an", "and", "or", "for", "with", "from", "new", "now",
     "get", "your", "this", "that", "free", "offer", "deal", "official"}
)


def _age_hours(published_at: Any, now: datetime) -> float | None:
    if not published_at:
        return None
    if isinstance(published_at, str):
        try:
            published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(published_at, datetime):
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - published_at.astimezone(timezone.utc)).total_seconds() / 3600)


def keyword_hits(text: str) -> list[str]:
    """Keywords present in title/excerpt, deduplicated in first-seen order."""
    lowered = (text or "").lower()
    return [word for word in _HIGH_INTENT if word in lowered]


def _signal_keywords(text: str) -> list[str]:
    """Short, human-readable keyword phrases for the dashboard chips."""
    hits = keyword_hits(text)
    return hits[:8]


def _title_quality(title: str) -> int:
    words = [w for w in (title or "").replace("—", " ").replace("-", " ").split()
             if w.strip()]
    distinctive = [w for w in words if w.lower().strip(".,:;!?()[]") not in _GENERIC_TITLE_WORDS]
    if not words:
        return 0
    if len(distinctive) >= 4:
        return 12
    if len(distinctive) >= 2:
        return 8
    return 3


def _freshness(age_hours: float | None) -> int:
    if age_hours is None:
        return 55
    if age_hours <= 24:
        return 100
    if age_hours <= 72:
        return 88
    if age_hours <= 168:
        return 70
    if age_hours <= 720:
        return 42
    return 18


def _competition_gap(existing_offer_count: int, duplicate_count: int) -> int:
    """Fewer near-identical offers and duplicates means a clearer angle."""
    base = 78 - min(48, existing_offer_count * 8) - min(28, duplicate_count * 4)
    return max(10, base)


def _audience_fit(countries: Iterable[str] | None, category: str | None) -> int:
    country_score = 42
    if countries:
        normalized = {str(c).upper() for c in countries}
        if normalized & _FRIENDLY_COUNTRIES:
            country_score = 78
        elif normalized:
            country_score = 52
    category_score = _AUDIENCE_CATEGORIES.get((category or "").lower(), 8)
    return min(100, round(country_score * 0.55 + category_score * 0.45 + 16))


def _monetization(text: str, category: str | None) -> int:
    score = 38
    lowered = (text or "").lower()
    if any(word in lowered for word in ("credit", "trial", "free", "voucher", "license")):
        score += 26
    if any(word in lowered for word in ("domain", "hosting", "cloud", "gpu", "api")):
        score += 12
    if (category or "").lower() in {"student_programs", "startup_perks", "cloud_platforms"}:
        score += 10
    return min(100, score)


def score_item(
    item: dict[str, Any],
    *,
    now: datetime | None = None,
    existing_offer_count: int = 0,
    duplicate_count: int = 0,
) -> dict[str, Any]:
    """Return a scored candidate payload ready for `trend_candidates`.

    `item` accepts the inbox shape (title, text, published_at, source_provider,
    source_category, trust_tier, country_scope, url).
    """
    now = now or datetime.now(timezone.utc)
    title = str(item.get("title") or item.get("canonical_url") or item.get("url") or "Untitled lead")
    text = " ".join(str(item.get(k) or "") for k in ("title", "text", "selection"))
    provider = item.get("source_provider") or item.get("provider") or "unknown source"
    category = item.get("source_category") or item.get("category")
    tier = item.get("trust_tier") or item.get("source_trust_tier")
    countries = item.get("country_scope") or item.get("countries") or []

    hits = keyword_hits(text)
    demand = min(100, 22 + len(hits) * 9 + _title_quality(title))
    age = _age_hours(item.get("published_at") or item.get("observed_at"), now)
    freshness = _freshness(age)
    feasibility = min(
        100,
        28
        + _SOURCE_TIER.get(str(tier or ""), 7)
        + (12 if item.get("url") or item.get("canonical_url") else 0)
        + (8 if provider and provider != "unknown source" else 0),
    )
    gap = _competition_gap(existing_offer_count, duplicate_count)
    fit = _audience_fit(countries, category)
    money = _monetization(text, category)

    score = round(
        demand * 0.28
        + freshness * 0.18
        + feasibility * 0.18
        + gap * 0.14
        + fit * 0.12
        + money * 0.10,
        2,
    )

    drivers = []
    if hits:
        drivers.append("offer intent: " + ", ".join(hits[:4]))
    if freshness >= 88:
        drivers.append("fresh lead (under 3 days)")
    if _SOURCE_TIER.get(str(tier or ""), 0) >= 18:
        drivers.append("provider-owned source")
    if fit >= 70:
        drivers.append("strong audience/region fit")
    if gap >= 65:
        drivers.append("uncrowded angle")
    if not drivers:
        drivers.append("worth a human look; signals are thin")

    risks = []
    if freshness <= 42:
        risks.append("lead may be stale — recheck the official page")
    if money < 55:
        risks.append("value angle is weak")
    if gap < 40:
        risks.append("many near-identical leads already exist")
    if not countries:
        risks.append("eligibility region not recorded")

    return {
        "item_id": item.get("id"),
        "title": title,
        "url": str(item.get("url") or item.get("canonical_url") or ""),
        "source_provider": provider,
        "source_category": category,
        "country_scope": list(countries) if isinstance(countries, (list, tuple)) else [str(countries)],
        "language": item.get("language") or "en",
        "demand_score": round(demand, 2),
        "freshness_score": round(freshness, 2),
        "feasibility_score": round(feasibility, 2),
        "competition_gap": round(gap, 2),
        "audience_fit": round(fit, 2),
        "monetization": round(money, 2),
        "score": score,
        "score_reason": {
            "why_now": drivers,
            "risks": risks,
            "keywords": _signal_keywords(text),
            "age_hours": round(age, 1) if age is not None else None,
        },
        "signals": {
            "keyword_hits": hits,
            "source_tier": tier,
            "existing_offers": existing_offer_count,
            "duplicates": duplicate_count,
        },
    }


def radar_bands(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group candidates into the dashboard's radar rings by score."""
    bands: dict[str, list[dict[str, Any]]] = {
        "hot": [], "warm": [], "watch": [], "cold": [],
    }
    for candidate in candidates:
        score = float(candidate.get("score") or 0)
        if score >= 78:
            bands["hot"].append(candidate)
        elif score >= 62:
            bands["warm"].append(candidate)
        elif score >= 45:
            bands["watch"].append(candidate)
        else:
            bands["cold"].append(candidate)
    return bands
