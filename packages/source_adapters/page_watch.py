"""Lightweight official-page change watcher.

For selected official pages (pricing, terms, changelogs) where we poll
directly instead of self-hosting changedetection.io. The external item id is
a content hash: unchanged pages dedupe to the same id (no new candidate);
any visible change produces exactly one new candidate.
"""

import hashlib
import re
from typing import Optional

from .client import Fetcher
from .models import RawItem

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def fetch_page_snapshot(url: str, fetcher: Optional[Fetcher] = None,
                        max_text_chars: Optional[int] = 2000) -> list[RawItem]:
    """Collectors use excerpts; verification requests untruncated snapshot text."""
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        resp = fetcher.fetch(url)
        content = resp.content
        digest = hashlib.sha256(content).hexdigest()
        html = resp.text

        title_match = _TITLE_RE.search(html)
        title = title_match.group(1).strip() if title_match else None
        body = _TAG_RE.sub(" ", html)
        body = re.sub(r"\s+", " ", body).strip()
        if max_text_chars is not None:
            body = body[:max_text_chars]

        return [
            RawItem(
                external_item_id=f"page:{digest[:16]}",
                url=str(resp.url),
                title=title,
                text=body,
            )
        ]
    finally:
        if own_fetcher:
            fetcher.close()
