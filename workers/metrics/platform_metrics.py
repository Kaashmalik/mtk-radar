"""Per-video audience metric parsers (v0.18, master plan §7 "analyse views …
engagement"). Pure functions: provider payload in, normalized snapshot out
(same field names as POST /schedules/{id}/metrics). Unknown/None fields stay
None — never guessed — so dashboards distinguish "no data" from zero.
"""

from typing import Any, Optional


def parse_youtube_analytics(payload: dict[str, Any]) -> dict[str, Optional[float]]:
    """YouTube Analytics API v2 report response → normalized snapshot.
    Response shape: {"columnHeaders": [{"name": "views", …}, …], "rows": [[…]]}.

    Raises ValueError when the payload has no rows — callers treat that as
    "no data yet" (videos answered but nothing measured) and skip the post.
    """
    rows = payload.get("rows") or []
    cols = [c.get("name") for c in payload.get("columnHeaders", [])]
    if not rows or not cols:
        raise ValueError("youtube analytics payload has no rows (video not yet measured)")
    report = dict(zip(cols, rows[0]))

    avg_watch = report.get("averageViewDuration")
    return {
        "views": _int(report.get("views")),
        "likes": _int(report.get("likes")),
        "comments": _int(report.get("comments")),
        "shares": _int(report.get("shares")),
        "impressions": _int(report.get("impressions")),
        "avg_watch_s": _float(avg_watch),
        "avg_view_duration_s": _float(avg_watch),
        "avg_view_percentage": _float(report.get("averageViewPercentage")),
        "ctr": _float(report.get("impressionClickThroughRate")),
        "retention_3s": _float(report.get("retention_3s")),
        "subscribers_gained": _int(report.get("subscribersGained")),
    }


def parse_graph_insights(payload: dict[str, Any]) -> dict[str, Optional[float]]:
    """Meta Graph `/{video_id}/video_insights` response → normalized snapshot.
    Shape: {"data": [{"name": "total_video_views", "values": [{"value": 12}]}, …]}.
    """
    named: dict[str, Any] = {}
    for entry in payload.get("data", []):
        values = entry.get("values") or [{}]
        named[entry.get("name", "")] = values[0].get("value")

    return {
        "views": _int(named.get("total_video_views")),
        "likes": _int(named.get("total_video_reactions")),
        "comments": _int(named.get("total_comments")),
        "shares": None,
        "impressions": _int(named.get("total_impressions")),
        "avg_watch_s": None,
        "avg_view_duration_s": None,
        "avg_view_percentage": None,
        "ctr": None,
        "retention_3s": None,
        "subscribers_gained": None,
    }


def _float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
