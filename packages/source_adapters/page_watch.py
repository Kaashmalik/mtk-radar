"""Lightweight official-page change watcher.

For selected official pages (pricing, terms, changelogs) where we poll
directly instead of self-hosting changedetection.io. The external item id is
a content hash: unchanged pages dedupe to the same id (no new candidate); any
visible change produces exactly one new candidate.

Verification passes a :class:`~source_adapters.egress.EgressPolicy`. That path
also returns the exact raw bytes and fetch provenance so the API can store and
audit what the provider actually served, instead of trusting derived text.
"""

import base64
import hashlib
import re
from typing import Optional

from .client import Fetcher
from .egress import EgressPolicy
from .models import RawItem

#: Bump whenever the HTML→text transformation changes, so stored snapshots
#: remain attributable to the parser that produced them.
PARSER_VERSION = "page_watch/1"

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def decode_body(body: bytes, content_type: str) -> tuple[str, str]:
    """Decode a body with its declared charset, recording what was used."""
    charset = "utf-8"
    for param in (content_type or "").split(";")[1:]:
        name, _, value = param.partition("=")
        if name.strip().lower() == "charset":
            charset = value.strip().strip("\"'") or "utf-8"
    try:
        return body.decode(charset, errors="replace"), charset
    except LookupError:
        return body.decode("utf-8", errors="replace"), "utf-8"


def fetch_page_snapshot(url: str, fetcher: Optional[Fetcher] = None,
                        max_text_chars: Optional[int] = 2000, *,
                        policy: Optional[EgressPolicy] = None,
                        resolver=None, clock=None) -> list[RawItem]:
    """Collectors use excerpts; verification requests untruncated snapshot text.

    With ``policy`` set, the fetch is bounded and hop-validated, and the item
    carries ``extra["raw_content_b64"]`` plus ``extra["provenance"]``.
    """
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        provenance = None
        raw_content_b64 = None
        if policy is not None:
            result = fetcher.safe_fetch(url, policy=policy, resolver=resolver, clock=clock)
            html, encoding = decode_body(result.body, result.content_type)
            provenance = {
                "requested_url": result.requested_url,
                "final_url": result.final_url,
                "http_status": result.status,
                "content_type": result.content_type,
                "fetched_at": result.fetched_at.isoformat(),
                "redirects": list(result.redirects),
                "raw_sha256": result.raw_sha256,
                "byte_length": len(result.body),
                "encoding": encoding,
                "parser_version": PARSER_VERSION,
            }
            raw_content_b64 = base64.b64encode(result.body).decode("ascii")
            final_url = result.final_url
        else:
            resp = fetcher.fetch(url)
            html = resp.text
            final_url = str(resp.url)

        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()

        title_match = _TITLE_RE.search(html)
        title = title_match.group(1).strip() if title_match else None
        body = _TAG_RE.sub(" ", html)
        body = re.sub(r"\s+", " ", body).strip()
        if max_text_chars is not None:
            body = body[:max_text_chars]

        extra = {}
        if provenance is not None:
            extra["provenance"] = provenance
            extra["raw_content_b64"] = raw_content_b64

        return [
            RawItem(
                external_item_id=f"page:{digest[:16]}",
                url=final_url,
                title=title,
                text=body,
                extra=extra,
            )
        ]
    finally:
        if own_fetcher:
            fetcher.close()
