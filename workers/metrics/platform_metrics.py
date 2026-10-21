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
        "impressions": None,  # needs the reporting API dimension; not in this pull
        "avg_watch_s": float(avg_watch) if avg_watch is not None else None,
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
        "impressions": None,
        "avg_watch_s": None,
    }


def _int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
