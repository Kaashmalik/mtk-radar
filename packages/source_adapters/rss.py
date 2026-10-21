"""RSS / Atom feed collector."""

from datetime import datetime, timezone
from typing import Optional

import feedparser

from .client import EgressPolicy, Fetcher
from .models import RawItem


def fetch_rss(
    feed_url: str,
    fetcher: Optional[Fetcher] = None,
    *,
    policy: Optional[EgressPolicy] = None,
) -> list[RawItem]:
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        resp = fetcher.fetch_policy(
            feed_url,
            headers={"Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, */*;q=0.8"},
            policy=policy,
        )
        parsed = feedparser.parse(resp.content)
        items: list[RawItem] = []
        for entry in parsed.entries[:30]:
            link = entry.get("link") or entry.get("id")
            if not link:
                continue
            external_id = entry.get("id") or link
            published = _to_datetime(entry.get("published_parsed") or entry.get("updated_parsed"))
            summary = entry.get("summary") or entry.get("description") or ""
            items.append(
                RawItem(
                    external_item_id=str(external_id),
                    url=link,
                    title=entry.get("title"),
                    published_at=published,
                    text=_clean(summary)[:1000],
                )
            )
        return items
    finally:
        if own_fetcher:
            fetcher.close()


def _to_datetime(struct) -> Optional[datetime]:
    if not struct:
        return None
    try:
        return datetime(*struct[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _clean(html: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()
