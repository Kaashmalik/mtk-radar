"""Hugging Face Daily Papers collector (official API — huggingface.co/api/daily_papers).

Hot AI research with a measurable community signal (upvotes). This is the
"research → video" source from the enhancement plan (2026-10-24, WP-A): the
HF Papers page linked by each item IS the discoverable evidence trail, while
the paper itself stays a **Tier-B lead** — any claim about models, results or
offers still verifies against official sources before a video touches it.

One item per paper, ever: ``external_item_id`` is the stable arXiv id, so a
re-polled day dedupes instead of churning the inbox. Upvote growth velocity is
the radar's job (re-scoring), not the collector's.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional, Union

from .client import EgressPolicy, Fetcher
from .models import RawItem
from .trendcache import JsonCache, cached_json

_API = "https://huggingface.co/api/daily_papers"
CACHE_TTL_S = 6 * 3600  # the feed updates daily; refresh twice a day at most


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


def _clean(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text or "").strip()


def fetch_hf_daily_papers(
    published_date: Union[None, date, str] = None,
    limit: int = 30,
    fetcher: Optional[Fetcher] = None,
    token: Optional[str] = None,
    *,
    policy: Optional[EgressPolicy] = None,
    cache: Optional[JsonCache] = None,
) -> list[RawItem]:
    limit = max(1, min(int(limit), 100))
    params: dict[str, Any] = {"limit": limit}
    date_key = "today"
    if published_date is not None:
        date_key = (
            published_date.isoformat()
            if isinstance(published_date, date)
            else str(published_date)
        )
        params["date"] = date_key

    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        def load() -> list:
            resp = fetcher.fetch_policy(_API, headers=headers, params=params, policy=policy)
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError("unrecognized daily_papers payload shape")
            return data

        entries = cached_json(cache, f"hf_papers:{date_key}:{limit}", CACHE_TTL_S, load)

        items: list[RawItem] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            paper = entry.get("paper") if isinstance(entry.get("paper"), dict) else {}
            paper_id = paper.get("id")
            if not paper_id:
                continue
            title = _clean(paper.get("title") or "")
            summary = _clean(paper.get("summary") or "")
            try:
                upvotes = int(paper.get("upvotes") or 0)
            except (TypeError, ValueError):
                upvotes = 0
            items.append(
                RawItem(
                    external_item_id=f"hf-paper:{paper_id}",
                    url=f"https://huggingface.co/papers/{paper_id}",
                    title=f"[Paper] {title}" if title else None,
                    published_at=_to_datetime(entry.get("publishedAt")),
                    text=(
                        f"{summary[:600]} "
                        f"Signal: {upvotes} community upvotes on HF Daily Papers."
                    ).strip(),
                    extra={
                        "arxiv_id": str(paper_id),
                        "upvotes": upvotes,
                        "source_kind": "research_paper",
                    },
                )
            )
        return items
    finally:
        if own_fetcher:
            fetcher.close()
