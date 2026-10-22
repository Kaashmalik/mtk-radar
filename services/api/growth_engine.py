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

from statistics import mean
from typing import Any, Iterable


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


def growth_score(rows: Iterable[dict[str, Any]]) -> float:
    """Blend the signals we actually have, without inventing missing ones."""
    rows = [r for r in rows if r]
    if not rows:
        return 0.0

    reach = [_num(r.get("views") or r.get("impressions")) for r in rows]
    engagement = [engagement_rate(r.get("views"), r.get("likes"), r.get("comments")) for r in rows]
    retention = [
        _num(r.get("retention_3s")) * 100
        if r.get("retention_3s") is not None
        else _num(r.get("avg_view_duration_s"))
        for r in rows
    ]
    clicks = [_num(r.get("link_clicks")) for r in rows]

    # Normalize each signal to 0–100 with transparent, conservative ceilings.
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
    if any(r.get("retention_3s") is not None or r.get("avg_view_duration_s") is not None
           for r in rows):
        available.append((retention_score, 0.25))
    if any(r.get("link_clicks") is not None for r in rows):
        available.append((click_score, 0.10))
    total_weight = sum(weight for _score, weight in available)
    if total_weight == 0:
        return 0.0
    blended = sum(score * weight for score, weight in available) / total_weight
    return _clamp_score(blended)


def _best_by(rows: list[dict[str, Any]], key: str,
             value_key: str = "views") -> tuple[str, float] | None:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        label = str(row.get(key) or "unknown")
        grouped.setdefault(label, []).append(_num(row.get(value_key) or row.get("views")))
    if not grouped:
        return None
    label, values = max(grouped.items(), key=lambda pair: mean(pair[1]) if pair[1] else 0)
    return label, round(mean(values), 1)


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
    best_language = _best_by(languages or rows, "language", "avg_views")
    avg_engagement = mean([engagement_rate(r.get("views"), r.get("likes"), r.get("comments"))
                           for r in rows]) if rows else 0
    avg_retention = mean([_num(r.get("retention_3s")) for r in rows
                          if r.get("retention_3s") is not None]) if any(
        r.get("retention_3s") is not None for r in rows) else 0

    if best_platform:
        out.append({
            "priority": "high",
            "title": f"Double down on {best_platform[0]}",
            "detail": f"{best_platform[0]} leads the current set at ~{best_platform[1]:.0f} "
                      "views per measured post. Reuse its hook length, cover style and "
                      "posting window for the next three posts.",
            "metric": "reach",
        })
    if best_language and best_language[1] > 0:
        out.append({
            "priority": "medium",
            "title": f"Prioritize {best_language[0]} on the next production run",
            "detail": f"The {best_language[0]} variant currently leads on average views. "
                      "Keep both languages, but sequence the stronger one first.",
            "metric": "language",
        })
    if avg_retention and avg_retention < 0.45:
        out.append({
            "priority": "high",
            "title": "Shorten the hook and show proof sooner",
            "detail": f"Average 3-second retention is {avg_retention * 100:.0f}%. Move the "
                      "official-terms/proof frame into the first 3 seconds and cut the "
                      "intro card to under 1 second.",
            "metric": "retention",
        })
    if avg_engagement < 3:
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

    return {
        "score": growth_score(rows),
        # This is an internal directional blend of the fields the platform
        # happened to expose. It is not a platform metric or a compliance
        # signal; label it that way wherever it is displayed.
        "score_label": "internal directional health signal, not a platform metric",
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
