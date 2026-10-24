"""Google Trends 'trending now' collector (public RSS endpoint — Tier-B leads).

Google's official Trends API is still an application-gated alpha (announced
July 2025) and the old realtime endpoints are dead, but the ``/trending/rss``
feed remains a public, documented-by-observation snapshot of what a region is
searching *right now*. It is the cheapest "is the wider public waking up to
this topic?" signal available without scraping the Trends UI.

**Fail-open by design and Tier-B by policy:** the feed is unofficial, its
schema can change, and a trending search is a topic proposal — never evidence.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional
from urllib.parse import quote_plus

import feedparser

from .client import EgressPolicy, Fetcher
from .models import RawItem
from .trendcache import JsonCache, cached_json

_RSS = "https://trends.google.com/trending/rss"
_GEO_RE = re.compile(r"^[A-Z]{2}$")
CACHE_TTL_S = 6 * 3600  # the trending snapshot refreshes on Google's schedule


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch_google_trends_trending(
    geo: str = "US",
    fetcher: Optional[Fetcher] = None,
    *,
    policy: Optional[EgressPolicy] = None,
    cache: Optional[JsonCache] = None,
) -> list[RawItem]:
    geo = (geo or "").strip().upper()
    if not _GEO_RE.match(geo):
        raise ValueError(f"invalid geo code: {geo!r}")

    params = {"geo": geo}
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        def load() -> bytes:
            resp = fetcher.fetch_policy(
                _RSS,
                headers={"Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"},
                params=params,
                policy=policy,
            )
            return resp.content

        body = cached_json(cache, f"gtrends:{geo}", CACHE_TTL_S, load)
        # A cached hit is already bytes; feedparser accepts both bytes and text.
        parsed = feedparser.parse(body if isinstance(body, (bytes, bytearray)) else str(body).encode())

        items: list[RawItem] = []
        for entry in parsed.entries[:30]:
            query = _clean(entry.get("title"))
            if not query:
                continue
            traffic = _clean(entry.get("ht_approx_traffic"))
            news_items = entry.get("ht_news_item") or []
            if isinstance(news_items, dict):
                news_items = [news_items]
            headlines = "; ".join(
                filter(None, (_clean(n.get("ht_news_item_title")) for n in news_items[:2]
                              if isinstance(n, dict)))
            )
            if not headlines:
                # feedparser hoists a lone <ht:news_item_title> to entry level.
                headlines = _clean(entry.get("ht_news_item_title"))
            digest = hashlib.sha256(query.lower().encode("utf-8")).hexdigest()[:16]
            items.append(
                RawItem(
                    # Stable per query+geo: a query that stays trending across
                    # sweeps dedupes to nothing instead of churning the inbox.
                    external_item_id=f"gt:{geo}:{digest}",
                    url=f"https://trends.google.com/trends/explore?q={quote_plus(query)}",
                    title=f"Trending search: {query}",
                    text=(
                        f"'{query}' is trending on Google ({geo}). "
                        f"Approx traffic: {traffic or 'n/a'}. "
                        + (f"News: {headlines}. " if headlines else "")
                        + "Signal: trending-now placement (24h window)."
                    ).strip(),
                    extra={
                        "geo": geo,
                        "approx_traffic": traffic,
                        "query": query,
                        "source_kind": "trend_signal",
                    },
                )
            )
        return items
    finally:
        if own_fetcher:
            fetcher.close()
