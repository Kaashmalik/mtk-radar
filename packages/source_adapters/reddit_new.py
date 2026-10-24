"""Public subreddit collector (public JSON endpoint, Tier-B lead signals).

Reads only what any anonymous visitor sees: ``/r/<sub>/new.json`` with a
descriptive User-Agent, one small page per poll — squarely inside Reddit's
polite-usage guidance and far below any quota surface. Upvote/comment counts
give the radar a community-momentum signal. Posts are leads only: a popular
thread proposes a topic, it never verifies an offer.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from .client import EgressPolicy, Fetcher
from .models import RawItem
from .trendcache import JsonCache, cached_json

_SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{1,20}$")
CACHE_TTL_S = 30 * 60


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch_reddit_new(
    subreddit: str,
    *,
    min_score: int = 25,
    max_age_hours: int = 48,
    limit: int = 25,
    fetcher: Optional[Fetcher] = None,
    policy: Optional[EgressPolicy] = None,
    cache: Optional[JsonCache] = None,
) -> list[RawItem]:
    subreddit = (subreddit or "").strip().strip("/")
    if not _SUBREDDIT_RE.match(subreddit):
        raise ValueError(f"invalid subreddit identifier: {subreddit!r}")
    min_score = max(0, int(min_score))
    max_age_hours = max(0, int(max_age_hours))
    limit = max(1, min(int(limit), 50))

    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    params = {"limit": limit, "raw_json": "1"}

    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        def load() -> dict:
            resp = fetcher.fetch_policy(
                url, headers={"Accept": "application/json"}, params=params, policy=policy
            )
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("unrecognized reddit payload shape")
            return data

        data = cached_json(
            cache,
            f"reddit:{subreddit}:{min_score}:{max_age_hours}:{limit}",
            CACHE_TTL_S,
            load,
        )

        cutoff = (
            datetime.now(timezone.utc).timestamp() - max_age_hours * 3600
            if max_age_hours
            else 0.0
        )
        items: list[RawItem] = []
        for child in (data.get("data") or {}).get("children") or []:
            if not isinstance(child, dict):
                continue
            post = child.get("data") if isinstance(child.get("data"), dict) else {}
            post_id = post.get("id")
            permalink = post.get("permalink")
            if not post_id or not permalink:
                continue
            try:
                score = int(post.get("score") or 0)
                comments = int(post.get("num_comments") or 0)
                created = float(post.get("created_utc") or 0.0)
            except (TypeError, ValueError):
                continue
            if score < min_score:
                continue
            if max_age_hours and (not created or created < cutoff):
                continue
            title = _clean(post.get("title"))
            body = _clean(post.get("selftext"))[:400]
            items.append(
                RawItem(
                    external_item_id=f"reddit:{post_id}",
                    url=f"https://www.reddit.com{permalink}",
                    title=title or None,
                    published_at=(
                        datetime.fromtimestamp(created, tz=timezone.utc) if created else None
                    ),
                    text=(
                        f"{body} Signal: {score} upvotes, {comments} comments "
                        f"on r/{subreddit}."
                    ).strip(),
                    extra={
                        "reddit_score": score,
                        "reddit_comments": comments,
                        "subreddit": subreddit,
                        "source_kind": "trend_signal",
                    },
                )
            )
        return items
    finally:
        if own_fetcher:
            fetcher.close()
