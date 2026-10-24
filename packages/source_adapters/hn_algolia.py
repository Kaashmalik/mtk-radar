"""Hacker News story collector via the free, key-less Algolia search API.

Point velocity on HN is one of the strongest "the developer world is talking
about this" signals, and hn.algolia.com/api/v1 is an official, documented,
free endpoint — no scraping involved. Stories are **Tier-B leads**: a heated
discussion proposes a topic; it never verifies an offer.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Optional

from .client import EgressPolicy, Fetcher
from .models import RawItem
from .trendcache import JsonCache, cached_json

_API = "https://hn.algolia.com/api/v1/search_by_date"
CACHE_TTL_S = 30 * 60  # a busy search page turns over faster than its cache


def _clean(html: Optional[str]) -> str:
    if not html:
        return ""
    import html as html_lib

    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _to_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_hn_stories(
    query: str,
    *,
    min_points: int = 50,
    max_age_hours: int = 72,
    limit: int = 20,
    fetcher: Optional[Fetcher] = None,
    policy: Optional[EgressPolicy] = None,
    cache: Optional[JsonCache] = None,
) -> list[RawItem]:
    query = (query or "").strip()
    if not query:
        raise ValueError("hn_search source missing config.query")
    limit = max(1, min(int(limit), 50))
    min_points = max(0, int(min_points))
    max_age_hours = max(0, int(max_age_hours))

    numeric_filters = [f"points>={min_points}"]
    if max_age_hours:
        since = int(time.time()) - max_age_hours * 3600
        numeric_filters.append(f"created_at_i>{since}")
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": ",".join(numeric_filters),
        "hitsPerPage": limit,
    }

    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        def load() -> dict:
            resp = fetcher.fetch_policy(
                _API, headers={"Accept": "application/json"}, params=params, policy=policy
            )
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("unrecognized algolia payload shape")
            return data

        data = cached_json(
            cache, f"hn:{query}:{min_points}:{max_age_hours}:{limit}", CACHE_TTL_S, load
        )

        items: list[RawItem] = []
        cutoff = (
            time.time() - max_age_hours * 3600 if max_age_hours else 0.0
        )
        for hit in data.get("hits") or []:
            if not isinstance(hit, dict):
                continue
            story_id = hit.get("objectID")
            if not story_id:
                continue
            try:
                points = int(hit.get("points") or 0)
                comments = int(hit.get("num_comments") or 0)
            except (TypeError, ValueError):
                continue
            # Server-side numericFilters is the primary filter; these guards
            # keep the adapter honest if the API ever loosens a filter.
            if points < min_points:
                continue
            published_at = _to_datetime(hit.get("created_at"))
            if max_age_hours:
                if published_at is None:
                    continue  # no timestamp → cannot prove freshness
                if published_at.timestamp() < cutoff:
                    continue
            title = _clean(hit.get("title") or "")
            body = _clean(hit.get("story_text") or "")[:400]
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
            items.append(
                RawItem(
                    external_item_id=f"hn:{story_id}",
                    url=url,
                    title=title or None,
                    published_at=published_at,
                    text=(
                        f"{body} "
                        f"Signal: {points} points, {comments} comments on Hacker News."
                    ).strip(),
                    extra={
                        "hn_points": points,
                        "hn_comments": comments,
                        "hn_object_id": str(story_id),
                        "source_kind": "trend_signal",
                    },
                )
            )
        return items
    finally:
        if own_fetcher:
            fetcher.close()
