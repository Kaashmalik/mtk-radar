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

import math
import re
from datetime import datetime, timezone
from typing import Any, Final, Iterable, Optional

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
    # Trend-signal sources (WP-A, enhancement plan 2026-10-24): papers score a
    # touch higher than social feeds because an upvoted paper implies many
    # independent researchers judged the story interesting.
    "research_papers": 12, "trend_signals": 8,
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

#: The 2026 playbook's "3-competitor" rule: a topic is actively trending when
#: similar channels with 10k-100k subscribers get views above their subscriber
#: count. Below 10k the sample is noise; above 100k the niche is proven but
#: you are competing with established channels, not joining a wave.
COMPETITOR_SUB_BAND: Final[tuple[float, float]] = (10_000.0, 100_000.0)

# ------------------------------------------------------ velocity (WP-B)
# A candidate re-scored at least this many hours after its previous
# observation produces a fresh velocity sample; anything sooner is noise.
VELOCITY_MIN_GAP_H: Final[float] = 1.0
#: Past this gap the previous velocity says nothing about "now" — the instant
#: rate alone is used, no smoothing.
VELOCITY_STALE_H: Final[float] = 48.0
CORROBORATION_BUMP_PER_SOURCE: Final[float] = 3.0
CORROBORATION_BUMP_CAP: Final[float] = 10.0

# ------------------------------------------------- observed engagement (G08)
#: Momentum must come from OBSERVED engagement (raw count deltas with
#: timestamps) — never from internal score movement, which mixes in freshness
#: and keyword facets and could dress a retitle up as a rising trend.
ENGAGEMENT_METRIC_PRIORITY: Final[tuple[str, ...]] = (
    "points", "upvotes", "stars", "comments")
ENGAGEMENT_BUMP_BASE: Final[float] = 6.0
ENGAGEMENT_BUMP_CAP: Final[float] = 15.0

# ------------------------------------------------- typed measurements (G07/G08)
#: Adapter payload keys (RawItem.extra) that carry OBSERVED engagement
#: counts, mapped to their canonical measurement name. A raw count the source
#: published is the only honest momentum input: score changes mix in
#: freshness and keyword facets (G08), so velocity must come from deltas of
#: THESE numbers, never from internal score movement.
MEASUREMENT_SOURCES: Final[dict[str, str]] = {
    "hn_points": "points",        # Hacker News story points
    "hn_comments": "comments",    # Hacker News comment count
    "reddit_score": "points",     # Reddit post score
    "reddit_comments": "comments",
    "upvotes": "upvotes",         # HF Daily Papers community upvotes
    "stars": "stars",             # GitHub star snapshot
}


def measurement_from_extra(extra: Any) -> dict[str, float]:
    """Typed numeric engagement counts from an adapter payload (G07).

    Only clean numbers survive: a missing count stays missing (the radar
    never interpolates "unknown"), and textual metrics ("approx traffic:
    20000+") are context, not measurements.
    """
    if not isinstance(extra, dict):
        return {}
    out: dict[str, float] = {}
    for key, name in MEASUREMENT_SOURCES.items():
        value = extra.get(key)
        if isinstance(value, bool) or value is None:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        if num >= 0 and num == num:  # finite, non-negative
            out[name] = num
    return out


def story_key(title: Any) -> Optional[str]:
    """Cross-URL same-story clustering key (G09).

    `duplicate_group` is the canonical URL: the SAME story republished at a
    different URL (syndication, a platform mirror, an updated permalink) got
    a different group and its independent confirmations were invisible. The
    story key clusters by the headline the way a human would: case-,
    punctuation- and whitespace-insensitive, with common filler words
    dropped. Deliberately conservative — it is a SIGNAL AGGREGATION key
    (corroboration counts), never a dedup key: `items` UNIQUE constraints
    remain the only story-dedup mechanism, so two genuinely different stories
    with similar titles are scored separately.
    """
    text = str(title or "").lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    filler = {"the", "a", "an", "of", "for", "to", "on", "in", "and", "or",
              "is", "are", "with", "at", "by", "from", "its", "it", "this",
              "that", "as", "be", "was", "were", "new"}
    words = [w for w in tokens if w not in filler]
    if len(words) < 3:
        return None  # too thin to cluster honestly
    return "story:" + "-".join(words[:12])


def engagement_rate(samples: list[tuple[Any, dict[str, Any]]]) -> dict[str, Any]:
    """Raw engagement delta per hour between the two most recent observations
    of the same entity (G08).

    `samples` is any-order list of ``(observed_at, measurements_dict)``.
    Only OBSERVED source counts drive momentum: a missing measurement stays
    unknown (no interpolation), identical counts stay flat (unchanged fields
    cannot fake a rising trend), and a falling count is honest cooling.

    Returns ``{known, metric, per_h, window_h, delta}`` — ``known: False``
    whenever momentum cannot be measured from real data.
    """
    unknown = {"known": False, "metric": None, "per_h": None,
               "window_h": None, "delta": None}
    clean: list[tuple[datetime, dict[str, float]]] = []
    for observed_at, measurements in samples or []:
        if isinstance(observed_at, str):
            try:
                observed_at = datetime.fromisoformat(
                    str(observed_at).replace("Z", "+00:00"))
            except ValueError:
                continue
        if not isinstance(observed_at, datetime):
            continue
        if not isinstance(measurements, dict):
            continue
        clean.append((observed_at, measurements))
    if len(clean) < 2:
        return {**unknown, "reason": "fewer than two observations"}

    clean.sort(key=lambda s: s[0])
    (t_prev, m_prev), (t_last, m_last) = clean[-2], clean[-1]
    window_h = (t_last - t_prev).total_seconds() / 3600.0
    if window_h <= 0:
        return {**unknown, "reason": "non-positive observation window"}

    for metric in ENGAGEMENT_METRIC_PRIORITY:
        prev_v, last_v = m_prev.get(metric), m_last.get(metric)
        try:
            prev_v = float(prev_v)          # type: ignore[arg-type]
            last_v = float(last_v)          # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue  # metric missing (or textual) in either sample → unknown
        delta = last_v - prev_v
        return {
            "known": True,
            "metric": metric,
            "per_h": round(delta / window_h, 3),
            "window_h": round(window_h, 3),
            "delta": round(delta, 3),
        }
    return {**unknown, "reason": "no shared measurable metric"}


def engagement_bump(engagement: Any) -> float:
    """Capped demand bonus from OBSERVED engagement growth (G08).

    Log-scaled against the raw rate (points/hour) so one huge spike cannot
    dominate, and so the strongest risers hit the same cap the momentum slot
    always had. Unknown (missing) engagement and flat/cooling counts bump
    nothing — the absence of data is never read as popularity.
    """
    if not isinstance(engagement, dict) or not engagement.get("known"):
        return 0.0
    rate = _num(engagement.get("per_h"))
    if rate <= 0:
        return 0.0
    return round(min(ENGAGEMENT_BUMP_CAP,
                     ENGAGEMENT_BUMP_BASE * math.log10(1.0 + rate)), 3)


def smooth_velocity(
    prev_score: Any,
    new_score: Any,
    prev_observed_at: Any,
    now: datetime,
    prev_velocity: Any = 0.0,
) -> float:
    """Score delta per hour, EMA-smoothed over the previous sample.

    Pure function over stored values so any number on the radar can be
    recomputed. Before the first reliable gap (VELOCITY_MIN_GAP_H) the stored
    velocity is kept unchanged; past VELOCITY_STALE_H the instant rate is used
    alone.
    """
    prev_velocity = _num(prev_velocity)
    prev = _num(prev_score)
    new = _num(new_score)
    if prev_observed_at is None:
        return prev_velocity
    if isinstance(prev_observed_at, str):
        try:
            prev_observed_at = datetime.fromisoformat(
                str(prev_observed_at).replace("Z", "+00:00"))
        except ValueError:
            return prev_velocity
    if not isinstance(prev_observed_at, datetime):
        return prev_velocity
    if prev_observed_at.tzinfo is None:
        prev_observed_at = prev_observed_at.replace(tzinfo=timezone.utc)
    hours = (now - prev_observed_at.astimezone(timezone.utc)).total_seconds() / 3600
    if hours < VELOCITY_MIN_GAP_H:
        return prev_velocity  # too soon for a meaningful sample
    instant = (new - prev) / hours
    if hours > VELOCITY_STALE_H or prev_velocity <= 0:
        return round(instant, 3)
    return round(0.6 * prev_velocity + 0.4 * instant, 3)


def corroboration_bump(corroborating_sources: Any) -> float:
    sources = int(_num(corroborating_sources))
    if sources < 2:
        return 0.0
    return min(CORROBORATION_BUMP_CAP, (sources - 1) * CORROBORATION_BUMP_PER_SOURCE)


def _num(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def competitor_evidence(competitors: Iterable[Any] | None) -> dict[str, Any]:
    """Parse raw competitor channel stats into a transparent demand verdict.

    Accepts dicts like {"channel": "Name", "subscribers": 42000,
    "views_28d": 91000} (aliases: subs/recent_views/views). Returns how many
    similar channels fall inside the 10k-100k band and how many of those
    out-perform their subscriber count.
    """
    parsed: list[dict[str, Any]] = []
    for entry in competitors or []:
        if not isinstance(entry, dict):
            continue
        subs = _num(entry.get("subscribers") or entry.get("subs"))
        if subs <= 0:
            continue
        parsed.append({
            "channel": str(entry.get("channel") or entry.get("name") or "channel"),
            "subscribers": subs,
            "recent_views": _num(
                entry.get("views_28d") or entry.get("recent_views") or entry.get("views")),
        })
    low, high = COMPETITOR_SUB_BAND
    in_band = [c for c in parsed if low <= c["subscribers"] <= high]
    demand_hits = [c for c in in_band if c["recent_views"] > c["subscribers"]]
    return {
        "provided": len(parsed),
        "in_band": len(in_band),
        "demand_hits": len(demand_hits),
        "sample_ok": len(in_band) >= 3,
        "channels": [
            {"channel": c["channel"], "subscribers": c["subscribers"],
             "recent_views": c["recent_views"], "outsizes_subs": c in demand_hits}
            for c in in_band
        ],
    }


def _competitor_bump(evidence: dict[str, Any]) -> float:
    """Deterministic demand bonus from verified competitor evidence."""
    if not evidence["sample_ok"] or not evidence["demand_hits"]:
        return 0.0
    return min(20.0, 8.0 + 6.0 * evidence["demand_hits"])



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


def _composite(demand: float, freshness: float, feasibility: float,
               gap: float, fit: float, money: float) -> float:
    """The one score blend. Weights are order-stable and re-used everywhere a
    component is re-computed (e.g. competitor evidence updates)."""
    return round(
        demand * 0.28
        + freshness * 0.18
        + feasibility * 0.18
        + gap * 0.14
        + fit * 0.12
        + money * 0.10,
        2,
    )


def apply_competitor_evidence(candidate: dict[str, Any],
                              competitors: Iterable[Any] | None) -> dict[str, Any]:
    """Re-score a stored candidate after the operator records competitor stats.

    Pure function over the candidate row + fresh human research: bump the
    demand component per the 3-competitor rule, update the explanatory
    drivers/risks, and recompute the composite with the same weights. Nothing
    is invented — the bump only happens for channels the operator measured.
    """
    evidence = competitor_evidence(competitors)
    demand = _num(candidate.get("demand_score")) or 0.0
    bump = _competitor_bump(evidence)
    demand = min(100.0, demand + bump) if bump else demand

    reason = candidate.get("score_reason") if isinstance(candidate.get("score_reason"), dict) else {}
    reason = dict(reason)
    drivers = [str(d) for d in reason.get("why_now", [])]
    risks = [str(r) for r in reason.get("risks", [])]
    if evidence["sample_ok"] and evidence["demand_hits"]:
        drivers.append(
            f"3-competitor rule: {evidence['demand_hits']} of {evidence['in_band']} "
            "similar mid-size channels get more views than subscribers")
    elif evidence["sample_ok"] and not evidence["demand_hits"]:
        risks.append(
            "mid-size competitors cover this story without outsized views — "
            "demand unproven")
    if evidence["provided"] and not evidence["sample_ok"]:
        risks.append(
            "competitor sample is thin — find 3 similar channels with "
            "10k-100k subscribers before committing to this topic")
    reason["why_now"] = drivers
    reason["risks"] = risks

    signals = candidate.get("signals") if isinstance(candidate.get("signals"), dict) else {}
    signals = dict(signals)
    signals["competitor_evidence"] = {
        "provided": evidence["provided"],
        "in_band": evidence["in_band"],
        "demand_hits": evidence["demand_hits"],
        "sample_ok": evidence["sample_ok"],
        "channels": evidence["channels"],
    }

    out = dict(candidate)
    out["demand_score"] = round(demand, 2)
    out["score"] = _composite(
        demand, _num(candidate.get("freshness_score")),
        _num(candidate.get("feasibility_score")), _num(candidate.get("competition_gap")),
        _num(candidate.get("audience_fit")), _num(candidate.get("monetization")))
    out["score_reason"] = reason
    out["signals"] = signals
    return out


def score_item(
    item: dict[str, Any],
    *,
    now: datetime | None = None,
    existing_offer_count: int = 0,
    duplicate_count: int = 0,
    competitors: Iterable[Any] | None = None,
    velocity: Any = 0.0,
    corroborating_sources: int = 1,
    engagement: Any = None,
) -> dict[str, Any]:
    """Return a scored candidate payload ready for `trend_candidates`.

    `item` accepts the inbox shape (title, text, published_at, source_provider,
    source_category, trust_tier, country_scope, url). `competitors` optionally
    carries the operator's 3-competitor-rule research; demand is bumped only
    when at least 3 similar 10k-100k-subscriber channels out-perform their
    subscriber count. `engagement` (from trend_engine.engagement_rate — raw
    count deltas over time observed at the SOURCE) and `corroborating_sources`
    (independent providers on the same story) add transparent, capped demand
    bumps — momentum the radar measured, never invented. `velocity`
    (score/hour) is recorded as a DIAGNOSTIC only: since G08 it no longer
    moves demand, because internal score movement mixes in freshness and
    keyword facets — a retitle must not be able to fake a rising trend.
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

    # 2026 playbook: human competitor research (the "3-competitor" rule)
    # strengthens the demand component — never more than what was measured.
    comp = competitor_evidence(competitors)
    bump = _competitor_bump(comp)
    # Trend Radar v2/G08: momentum = OBSERVED engagement growth only; score
    # changes are a diagnostic of the candidate's own history.
    e_bump = engagement_bump(engagement)
    c_bump = corroboration_bump(corroborating_sources)
    if bump or e_bump or c_bump:
        demand = min(100.0, demand + bump + e_bump + c_bump)

    score = _composite(demand, freshness, feasibility, gap, fit, money)

    drivers = []
    if hits:
        drivers.append("offer intent: " + ", ".join(hits[:4]))
    if freshness >= 88:
        drivers.append("fresh lead (under 3 days)")
    if _SOURCE_TIER.get(str(tier or ""), 0) >= 18:
        drivers.append("provider-owned source")
    if _num(velocity) > 0:
        drivers.append(
            "score history rising (+{:.2g} score/hour, diagnostic)".format(
                _num(velocity)))
    if e_bump:
        eng = engagement if isinstance(engagement, dict) else {}
        drivers.append(
            f"observed engagement rising {_num(eng.get('per_h')):g} "
            f"{eng.get('metric')}/hour at the source")
    if c_bump:
        drivers.append(
            f"{int(corroborating_sources)} independent sources observed this story")
    if fit >= 70:
        drivers.append("strong audience/region fit")
    if gap >= 65:
        drivers.append("uncrowded angle")
    if bump:
        drivers.append(
            f"3-competitor rule: {comp['demand_hits']} of {comp['in_band']} "
            "similar mid-size channels get more views than subscribers")
    if not drivers:
        drivers.append("worth a human look; signals are thin")

    risks = []
    if freshness <= 42:
        risks.append("lead may be stale — recheck the official page")
    if velocity < 0:
        risks.append("score history falling (diagnostic)")
    if isinstance(engagement, dict) and engagement.get("known") \
            and _num(engagement.get("per_h")) < 0:
        risks.append("observed engagement is cooling at the source")
    if money < 55:
        risks.append("value angle is weak")
    if gap < 40:
        risks.append("many near-identical leads already exist")
    if not countries:
        risks.append("eligibility region not recorded")
    if comp["sample_ok"] and not comp["demand_hits"]:
        risks.append(
            "mid-size competitors cover this story without outsized views — "
            "demand unproven")
    if comp["provided"] and not comp["sample_ok"]:
        risks.append(
            "competitor sample is thin — find 3 similar channels with "
            "10k-100k subscribers before committing to this topic")

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
            "velocity": round(_num(velocity), 3),
            "engagement": engagement if isinstance(engagement, dict) else None,
            "corroborating_sources": int(_num(corroborating_sources)),
            "competitor_evidence": {
                "provided": comp["provided"],
                "in_band": comp["in_band"],
                "demand_hits": comp["demand_hits"],
                "sample_ok": comp["sample_ok"],
                "channels": comp["channels"],
            },
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
