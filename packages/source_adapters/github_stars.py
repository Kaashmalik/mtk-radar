"""GitHub star-velocity collector (official REST — docs.github.com/en/rest).

Release feeds say *what changed*; star velocity says *how fast the world is
adopting it* — a strong, money-free trend signal for repo-adjacent topics.

Entity-stable ingestion (G08): ``external_item_id`` is the repo — NOT the
star count — so re-polls dedupe to the same story while every poll's typed
star count lands in ``extra`` and becomes one timestamped row of the
append-only ``source_observations`` series. The radar's momentum is computed
from that series' deltas, never from item churn or title changes.

G14 [S12]: the optional GitHub token is actually SENT (it used to be
accepted and dropped, so every poll counted against anonymous limits), as a
scoped read-only credential the operator supplies; requests are conditional
(``If-None-Match`` from a cached ETag, 304 = unchanged) so a poll with no
star movement costs no body transfer, and the primary rate limit is honored
fail-closed: when GitHub reports ``x-ratelimit-remaining: 0`` the run stops
instead of hammering until 403.
"""

from __future__ import annotations

import re
from typing import Optional

from .client import EgressPolicy, Fetcher
from .models import RawItem
from .trendcache import JsonCache

_API = "https://api.github.com"
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_MAX_REPOS = 50  # one polite REST call per repo per poll
_ETAG_TTL_S = 30 * 24 * 3600  # etags survive long pauses; GitHub invalidates


def _etag_key(repo: str) -> str:
    return f"gh-stars:etag:{repo}"


def fetch_github_stars(
    repos: list[str] | str,
    fetcher: Optional[Fetcher] = None,
    token: Optional[str] = None,
    *,
    policy: Optional[EgressPolicy] = None,
    cache: Optional[JsonCache] = None,
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
        # G14: scoped credential actually transmitted (never logged).
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        items: list[RawItem] = []
        for repo in clean:
            request_headers = dict(headers)
            if cache is not None:
                etag = cache.get_text(_etag_key(repo))
                if etag:
                    request_headers["If-None-Match"] = etag
            try:
                resp = fetcher.fetch_policy(
                    f"{_API}/repos/{repo}", headers=request_headers, policy=policy
                )
            except Exception as exc:  # noqa: BLE001 — surface rate-limit refusals
                response = getattr(exc, "response", None)
                status = getattr(response, "status_code", None)
                if status in (403, 429):
                    retry_after = response.headers.get("retry-after")
                    raise RuntimeError(
                        f"github star poll refused for {repo} (HTTP {status}; "
                        + (f"retry after {retry_after}s" if retry_after
                           else "rate limit exhausted — poll later)")
                    ) from exc
                raise
            if resp.status_code == 304:
                # Conditional short-circuit: unchanged since the last poll.
                continue
            data = resp.json()
            # Honor the PRIMARY rate limit: stop before GitHub has to refuse.
            if resp.headers.get("x-ratelimit-remaining") == "0":
                reset = resp.headers.get("x-ratelimit-reset")
                raise RuntimeError(
                    "github API rate limit exhausted"
                    + (f" (resets at epoch {reset})" if reset else "")
                    + f" — {len(items)} snapshot(s) kept")
            # Remember the validator for the next sweep's conditional request.
            etag = resp.headers.get("etag")
            if cache is not None and etag:
                cache.set_text(_etag_key(repo), etag, _ETAG_TTL_S)
            try:
                stars = int(data.get("stargazers_count") or 0)
            except (TypeError, ValueError):
                continue
            description = re.sub(r"\s+", " ", str(data.get("description") or "")).strip()
            items.append(
                RawItem(
                    # Stable entity id (G08): the star SERIES lives in
                    # source_observations; an unchanged repo must dedupe to
                    # the same story, not churn a new item per poll.
                    external_item_id=f"gh-stars:{repo}",
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
