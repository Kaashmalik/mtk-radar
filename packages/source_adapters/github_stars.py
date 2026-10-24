"""GitHub star-velocity collector (official REST — docs.github.com/en/rest).

Release feeds say *what changed*; star velocity says *how fast the world is
adopting it* — a strong, money-free trend signal for repo-adjacent topics.

Change-only ingestion: ``external_item_id`` embeds the star count, so an
unchanged repo dedupes to nothing and a star change produces exactly one new
candidate. A repo's item series in the inbox is therefore a usable velocity
curve for the radar (WP-B) without the collector keeping any state.
"""

from __future__ import annotations

import re
from typing import Optional

from .client import EgressPolicy, Fetcher
from .models import RawItem

_API = "https://api.github.com"
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_MAX_REPOS = 50  # one polite REST call per repo per poll


def fetch_github_stars(
    repos: list[str] | str,
    fetcher: Optional[Fetcher] = None,
    token: Optional[str] = None,
    *,
    policy: Optional[EgressPolicy] = None,
) -> list[RawItem]:
    if isinstance(repos, str):
        repos = [repos]
    clean: list[str] = []
    for repo in repos or []:
        repo = str(repo).strip()
        if not repo:
            continue
        if not _REPO_RE.match(repo):
            raise ValueError(f"invalid repo identifier: {repo!r}")
        clean.append(repo)
    if not clean:
        raise ValueError("github_stars source missing config.repos")
    if len(clean) > _MAX_REPOS:
        raise ValueError(f"too many repos (max {_MAX_REPOS})")

    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        headers = {"Accept": "application/vnd.github+json"}
        items: list[RawItem] = []
        for repo in clean:
            resp = fetcher.fetch_policy(
                f"{_API}/repos/{repo}", headers=headers, policy=policy
            )
            data = resp.json()
            try:
                stars = int(data.get("stargazers_count") or 0)
            except (TypeError, ValueError):
                continue
            description = re.sub(r"\s+", " ", str(data.get("description") or "")).strip()
            items.append(
                RawItem(
                    # New item ONLY when the count changes (UNIQUE at the API).
                    external_item_id=f"gh-stars:{repo}:{stars}",
                    url=f"https://github.com/{repo}",
                    title=f"{repo} — {stars} GitHub stars",
                    text=(
                        f"{description[:400]} "
                        "Signal: GitHub star snapshot (change-only; the radar "
                        "computes velocity from this repo's item series)."
                    ).strip(),
                    extra={
                        "repo": repo,
                        "stars": stars,
                        "source_kind": "trend_signal",
                    },
                )
            )
        return items
    finally:
        if own_fetcher:
            fetcher.close()
