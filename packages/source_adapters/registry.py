"""Authoritative adapter registry (EP-02 G06).

One place answers "which source adapter kinds exist, what configuration do
they need, and who runs them". The API schema, the collector, the dashboard
form, the seed script and the tests all derive from this module — before,
`schemas.py` allowed only kinds ("rss", "github_releases", "page_watch",
"extension", "manual") while five implemented trend adapters
(`hf_papers`, `hn_search`, `github_stars`, `reddit_new`,
`google_trends_rss`) were creatable only by bypassing the API with SQL.
Registering a new adapter now means adding one entry here; a sync guard
test fails anywhere the layers drift.

`config_required` lists the config keys the adapter cannot run without —
the collector (and `SourceIn` validation) enforce these so a misconfigured
source fails at registration time instead of silently polling nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AdapterSpec:
    """Everything the layers need to know about one adapter kind."""

    kind: str
    label: str  # dashboard <select> text
    description: str
    collector_polled: bool  # False for sinks/imports the collector never runs
    config_required: tuple[str, ...] = ()
    config_optional: tuple[str, ...] = field(default_factory=tuple)


ADAPTERS: dict[str, AdapterSpec] = {
    spec.kind: spec
    for spec in (
        AdapterSpec(
            kind="rss",
            label="RSS / Atom feed",
            description="Poll an RSS/Atom feed for new entries.",
            collector_polled=True,
            config_required=("feed_url",),
        ),
        AdapterSpec(
            kind="github_releases",
            label="GitHub releases",
            description="Watch a repository's releases (owner/name).",
            collector_polled=True,
            config_required=("repo",),
        ),
        AdapterSpec(
            kind="page_watch",
            label="Web page (watch)",
            description="Snapshot a page and detect content changes.",
            collector_polled=True,
            config_required=("url",),
        ),
        AdapterSpec(
            kind="hf_papers",
            label="Hugging Face daily papers",
            description="Daily AI research papers with upvote counts (Tier-B).",
            collector_polled=True,
            config_optional=("date", "limit"),
        ),
        AdapterSpec(
            kind="hn_search",
            label="Hacker News search",
            description="Algolia HN search for stories above a point threshold.",
            collector_polled=True,
            config_required=("query",),
            config_optional=("min_points", "max_age_hours", "limit"),
        ),
        AdapterSpec(
            kind="github_stars",
            label="GitHub stars (velocity)",
            description="Change-only star snapshots for a repo list — a "
                        "momentum time series, not item detection.",
            collector_polled=True,
            config_required=("repos",),
        ),
        AdapterSpec(
            kind="reddit_new",
            label="Reddit new posts",
            description="Public subreddit /new.json leads (Tier-B).",
            collector_polled=True,
            config_required=("subreddit",),
            config_optional=("min_score", "max_age_hours", "limit"),
        ),
        AdapterSpec(
            kind="google_trends_rss",
            label="Google Trends (trending searches)",
            description="Daily trending-search RSS for a geo (Tier-B).",
            collector_polled=True,
            config_optional=("geo",),
        ),
        AdapterSpec(
            kind="extension",
            label="Browser extension saves",
            description="Items saved by reviewer/browser extension — never polled.",
            collector_polled=False,
        ),
        AdapterSpec(
            kind="manual",
            label="Manual (seed only)",
            description="Manually recorded sources (e.g. library collectors) — never polled.",
            collector_polled=False,
        ),
    )
}

#: Stable ordering for UI dropdowns and docs (polled kinds first).
ADAPTER_KINDS: tuple[str, ...] = tuple(ADAPTERS)


def get(kind: str) -> AdapterSpec:
    """Registry entry for a kind; raises KeyError for an unregistered kind."""
    return ADAPTERS[kind]


def is_registered(kind: str) -> bool:
    return kind in ADAPTERS


def missing_config(kind: str, config: dict) -> list[str]:
    """Required config keys absent from `config` (empty dict tolerated → all)."""
    spec = ADAPTERS.get(kind)
    if spec is None:
        return [f"unknown adapter kind {kind!r}"]
    have = config if isinstance(config, dict) else {}
    return [key for key in spec.config_required
            if not str(have.get(key) or "").strip()]
