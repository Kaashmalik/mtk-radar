"""Closed-loop growth analysis (v0.27).

Analytics used to be a scoreboard. This module turns the latest per-post
signals into an actionable, conservative briefing:

  * a 0–100 growth health score (reach, engagement, retention, conversion)
  * language/platform performance comparisons
  * explicit experiments and their outcomes
  * a ranked list of next actions

It is deterministic and read-only. It never changes verification state and
never claims causality from a tiny sample; recommendations say "test", not
"this caused views".
"""

from __future__ import annotations

import os
from statistics import mean
from typing import Any, Iterable

#: The composite score blends YouTube-derived fields into one internal number.
#: YouTube's Developer Policies restrict replacing API data with independently
#: calculated metrics without an approved compliance review, so the score is
#: OFF by default. The raw measured fields and the conservative per-signal
#: recommendations remain available; only the composite blend is gated.
GROWTH_SCORE_ENV = "MTK_ENABLE_GROWTH_SCORE"
_TRUTHY = {"1", "true", "yes", "on"}

#: G21 (evidence-to-video plan): the SAME compliance rationale that gates the
#: composite growth score applies to EVERY derived engagement blend built from
#: platform metrics — not only growth_engine. Affected paths today:
#:   * `GET /schedules/best-times` — views + 2×(likes+comments) composite;
#:   * hashtag generation's measured-performance lift
#:     (`hashtag_performance` rollup re-ranking/sinking tags).
#: OFF by default; raw native metrics (avg views per hour, per-tag measured
#: impressions as stored DATA) and documented editorial heuristics remain
#: available ungated. Opt in per deployment only after the compliance review.
DERIVED_ENGAGEMENT_ENV = "MTK_ENABLE_DERIVED_ENGAGEMENT"


def growth_score_enabled() -> bool:
    return os.environ.get(GROWTH_SCORE_ENV, "").strip().lower() in _TRUTHY


def derived_engagement_enabled() -> bool:
    """Permission switch for derived engagement blends (G21, off by default)."""
    return os.environ.get(DERIVED_ENGAGEMENT_ENV, "").strip().lower() in _TRUTHY


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def engagement_rate(views: Any, likes: Any, comments: Any) -> float:
    """Likes + comments per view, as a percentage (0 when no views)."""
    view_count = _num(views)
    if view_count <= 0:
        return 0.0
    return round((_num(likes) + _num(comments)) / view_count * 100, 2)


def _value(row: dict[str, Any], key: str) -> Any:
    """Return a measured value, preserving zero; do not fall through on 0."""
    value = row.get(key)
    return value if value is not None else None


def _retention_fraction(row: dict[str, Any]) -> float | None:
    """Retention as a 0..1 fraction, never as an unconverted duration.

    `avg_view_duration_s` is seconds and cannot share a percentage scale with
    `retention_3s`. If a provider reports only seconds, retention is genuinely
    unavailable for the score rather than silently normalised as a percentage.

    The two fraction-shaped keys use DIFFERENT units as stored:
    `retention_3s` is a 0..1 fraction, but `avg_view_percentage` is YouTube's
    averageViewPercentage on a 0..100 scale (e.g. 48.25). A raw percentage
    multiplied back by 100 in growth_score pinned the retention component at
    100 and produced wording like "4825%" — so values > 1 are normalized to a
    fraction. A fraction can never exceed 1, so the heuristic is unambiguous.
    """
    for key in ("retention_3s", "avg_view_percentage"):
        value = _value(row, key)
        if value is not None:
            frac = _num(value)
            return frac / 100 if frac > 1 else frac
    return None


def growth_score(rows: Iterable[dict[str, Any]]) -> float:
    """Blend the signals we actually have, without inventing missing ones."""
    rows = [r for r in rows if r]
    if not rows:
        return 0.0

    reach = [
        _num(value) for r in rows
        if (value := (_value(r, "views") if _value(r, "views") is not None
                      else _value(r, "impressions"))) is not None
    ]
    engagement = [engagement_rate(r.get("views"), r.get("likes"), r.get("comments"))
                  for r in rows if _num(_value(r, "views")) > 0]
    retention = [
        fraction * 100 for r in rows
        if (fraction := _retention_fraction(r)) is not None
    ]
    clicks = [_num(value) for r in rows if (value := _value(r, "link_clicks")) is not None]

    # Normalize each signal to 0-100 with transparent, conservative ceilings.
    reach_score = min(100.0, mean(reach) / 10_000 * 100) if reach else 0.0
    engagement_score = min(100.0, mean(engagement) / 8 * 100) if engagement else 0.0
    retention_score = min(100.0, mean(retention) / 45 * 100) if retention else 0.0
    click_score = min(100.0, mean(clicks) / 100 * 100) if clicks else 0.0

    # A measured zero is not a missing signal. If views exist, engagement is
    # known (and may honestly be 0%); if retention/a CTR were reported, a zero
    # value still belongs in the weighting. Only genuinely unavailable fields
    # are renormalized away.
    available: list[tuple[float, float]] = []
    if any(r.get("views") is not None or r.get("impressions") is not None for r in rows):
        available.append((reach_score, 0.40))
    if any(_num(r.get("views")) > 0 for r in rows):
        available.append((engagement_score, 0.25))
    if any(_retention_fraction(r) is not None for r in rows):
        available.append((retention_score, 0.25))
    if any(r.get("link_clicks") is not None for r in rows):
        available.append((click_score, 0.10))
    total_weight = sum(weight for _score, weight in available)
    if total_weight == 0:
        return 0.0
    blended = sum(score * weight for score, weight in available) / total_weight
    return _clamp_score(blended)


def _best_by(rows: list[dict[str, Any]], key: str,
             value_key: str = "views") -> tuple[str, float, int] | None:
    """Best group by a measured value. Returns (label, mean, post_count).

    A zero is a measured value and stays zero; it must not fall through to a
    different field. Groups without any measured value are ignored, and a
    missing/zero metric can never produce a "best" claim.
    """
    grouped: dict[str, list[float]] = {}
    for row in rows:
        value = _value(row, value_key)
        if value is None:
            continue
        label = str(row.get(key) or "unknown")
        grouped.setdefault(label, []).append(_num(value))
    if not grouped:
        return None
    label, values = max(grouped.items(), key=lambda pair: mean(pair[1]) if pair[1] else 0)
    average = mean(values) if values else 0.0
    if average <= 0:
        return None
    return label, round(average, 1), len(values)


def recommendations(
    rows: list[dict[str, Any]],
    *,
    languages: list[dict[str, Any]] | None = None,
    experiments: list[dict[str, Any]] | None = None,
    stale_topics: int = 0,
) -> list[dict[str, Any]]:
    """Ranked, evidence-backed next actions for the operator."""
    out: list[dict[str, Any]] = []
    if not rows:
        return [{
            "priority": "high",
            "title": "Publish the first measured post",
            "detail": "No per-post metrics yet. Publish a private test, then connect the "
                      "metrics worker so the growth loop has a baseline.",
            "metric": "measurement",
        }]

    best_platform = _best_by(rows, "platform")
    language_rows = languages or rows
    language_groups = {
        str(r.get("language") or "unknown") for r in language_rows if r.get("language")
    }
    best_language = _best_by(language_rows, "language", "avg_views")
    measured_engagement = [
        engagement_rate(r.get("views"), r.get("likes"), r.get("comments"))
        for r in rows if _num(_value(r, "views")) > 0
    ]
    avg_engagement = mean(measured_engagement) if measured_engagement else None
    measured_retention = [
        fraction for r in rows
        if (fraction := _retention_fraction(r)) is not None
    ]
    avg_retention = mean(measured_retention) if measured_retention else None
    retention_is_estimate = any(
        bool(r.get("retention_3s_estimated"))
        for r in rows if _value(r, "retention_3s") is not None
    )
    # 2026 playbook pivot thresholds, applied only to actually measured rows:
    # CTR below 4% -> change the thumbnail or title; average view duration
    # below 40% -> read the retention graph and cut the dead segment.
    measured_ctr = [
        _num(_value(r, "ctr")) for r in rows
        if _value(r, "ctr") is not None and _num(_value(r, "impressions")) > 0
    ]
    avg_ctr = mean(measured_ctr) if measured_ctr else None
    measured_avd = [
        _num(_value(r, "avg_view_percentage")) for r in rows
        if _value(r, "avg_view_percentage") is not None
    ]
    avg_avd = mean(measured_avd) if measured_avd else None

    # A platform recommendation needs a minimum sample and more than one post
    # on the winning platform. Two measured posts are a lead, not proof.
    if best_platform and len(rows) >= 3 and best_platform[2] >= 2:
        out.append({
            "priority": "high",
            "title": f"Test more posts on {best_platform[0]}",
            "detail": f"{best_platform[0]} leads this small measured set at "
                      f"~{best_platform[1]:.0f} views per post. This is an association, "
                      "not proof of cause: vary one packaging element at a time and "
                      "keep the posting window stable.",
            "metric": "reach",
        })
    if best_language and best_language[1] > 0 and len(language_groups) >= 2:
        out.append({
            "priority": "medium",
            "title": f"Sequence {best_language[0]} first on the next production run",
            "detail": f"The {best_language[0]} variant leads this small sample on average "
                      "views. Keep both languages, but test the stronger one first; do "
                      "not drop the other variant without a longer sample.",
            "metric": "language",
        })
    if avg_retention is not None and avg_retention < 0.45:
        shown = (f"about {avg_retention * 100:.0f}% (nearest retention-curve "
                 "bucket, not an exact 3-second measurement)"
                 if retention_is_estimate else f"{avg_retention * 100:.0f}%")
        out.append({
            "priority": "high",
            "title": "Shorten the hook and show proof sooner",
            "detail": f"Average 3-second retention is {shown}. Move the "
                      "official-terms/proof frame into the first 3 seconds and cut the "
                      "intro card to under 1 second.",
            "metric": "retention",
        })
    if avg_ctr is not None and avg_ctr < 4.0:
        out.append({
            "priority": "high",
            "title": "Swap the packaging: CTR is under 4%",
            "detail": f"Average impression CTR is {avg_ctr:.1f}%. Per the 2026 "
                      "playbook, change the thumbnail or title immediately — "
                      "one variable at a time (the studio A/B variants and "
                      "experiments exist for exactly this), then re-measure. "
                      "Do not touch the video itself while testing packaging.",
            "metric": "packaging",
        })
    if avg_avd is not None and avg_avd < 40.0:
        out.append({
            "priority": "high",
            "title": "Cut the dead segment from the next script",
            "detail": f"Average view duration is {avg_avd:.0f}% — below the "
                      "40% bar. Open the retention graph to find the exact "
                      "drop-off mark and cut that part from the next script; "
                      "if the drop is inside the first 30 seconds, the hook "
                      "needs the fix, not the middle.",
            "metric": "avd",
        })
    if avg_engagement is not None and avg_engagement < 3:
        out.append({
            "priority": "medium",
            "title": "Add one specific question CTA",
            "detail": "Engagement is below 3%. Ask a single eligibility question in the "
                      "pinned comment; do not add multiple CTAs.",
            "metric": "engagement",
        })
    if stale_topics:
        out.append({
            "priority": "medium",
            "title": f"Refresh {stale_topics} stale radar leads",
            "detail": "These leads are older than their freshness window. Recheck the "
                      "official page before scripting or dismiss them.",
            "metric": "discovery",
        })
    if experiments:
        running = [e for e in experiments if e.get("status") == "running"]
        if running:
            out.append({
                "priority": "low",
                "title": f"Let {len(running)} experiment(s) reach a decision",
                "detail": "Do not change multiple packaging variables at once; wait for "
                          "at least 7 days or 500 views before calling a winner.",
                "metric": "experiments",
            })
    return out[:6]


def summarize(
    rows: list[dict[str, Any]],
    *,
    languages: list[dict[str, Any]] | None = None,
    experiments: list[dict[str, Any]] | None = None,
    stale_topics: int = 0,
) -> dict[str, Any]:
    rows = [r for r in rows if r]
    by_platform: dict[str, dict[str, float]] = {}
    for row in rows:
        platform = str(row.get("platform") or "unknown")
        bucket = by_platform.setdefault(platform, {"posts": 0, "views": 0.0,
                                                   "engagement": 0.0, "reach": 0.0})
        bucket["posts"] += 1
        bucket["views"] += _num(row.get("views"))
        bucket["engagement"] += engagement_rate(row.get("views"), row.get("likes"), row.get("comments"))
        bucket["reach"] += _num(row.get("impressions"))
    for bucket in by_platform.values():
        if bucket["posts"]:
            bucket["engagement"] = round(bucket["engagement"] / bucket["posts"], 2)

    enabled = growth_score_enabled()
    return {
        # `None` is a deliberate "unavailable", not a measured zero. The
        # dashboard must not paint a 0/100 bar when the blend is disabled.
        "score": growth_score(rows) if enabled else None,
        "score_enabled": enabled,
        # This is an internal directional blend of the fields the platform
        # happened to expose. It is not a platform metric or a compliance
        # signal; label it that way wherever it is displayed.
        "score_label": (
            "internal directional health signal, not a platform metric"
            if enabled else
            "composite score disabled pending YouTube API compliance review"
        ),
        "measured_posts": len(rows),
        "by_platform": [
            {"platform": platform, **values}
            for platform, values in sorted(by_platform.items(),
                                           key=lambda pair: pair[1]["views"], reverse=True)
        ],
        "recommendations": recommendations(rows, languages=languages,
                                           experiments=experiments,
                                           stale_topics=stale_topics),
    }
