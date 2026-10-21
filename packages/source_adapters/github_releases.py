"""GitHub releases collector (official REST API — docs.github.com/en/rest/releases).

Only maintainer-owned repositories are polled (Tier-A rule: GitHub releases
count as provider-owned evidence only when the repo belongs to the provider).
"""

import re
from datetime import datetime, timezone
from typing import Optional

from .client import EgressPolicy, Fetcher
from .models import RawItem

_API = "https://api.github.com"
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def fetch_github_releases(
    repo: str,
    fetcher: Optional[Fetcher] = None,
    token: Optional[str] = None,
    per_page: int = 15,
    *,
    policy: Optional[EgressPolicy] = None,
) -> list[RawItem]:
    if not _REPO_RE.match(repo):
        raise ValueError(f"invalid repo identifier: {repo!r}")

    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = fetcher.fetch_policy(
            f"{_API}/repos/{repo}/releases",
            headers=headers,
            params={"per_page": per_page},
            policy=policy,
        )
        releases = resp.json()
        items: list[RawItem] = []
        for rel in releases:
            published = None
            if rel.get("published_at"):
                published = datetime.fromisoformat(rel["published_at"].replace("Z", "+00:00"))
            body = rel.get("body") or ""
            items.append(
                RawItem(
                    external_item_id=str(rel["id"]),
                    url=rel.get("html_url") or f"https://github.com/{repo}/releases",
                    title=rel.get("name") or rel.get("tag_name"),
                    published_at=published or datetime.now(timezone.utc),
                    text=body[:1500],
                    extra={"tag": rel.get("tag_name"), "repo": repo},
                )
            )
        return items
    finally:
        if own_fetcher:
            fetcher.close()
