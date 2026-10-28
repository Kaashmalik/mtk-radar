"""Trend-signal adapters (enhancement plan 2026-10-24, WP-A).

Coverage: Hugging Face Daily Papers, Hacker News (Algolia), GitHub star
snapshots, Reddit public new-posts, Google Trends RSS, and the shared
JsonCache. Every adapter runs against a canned FakeFetcher — no network,
same fetch_policy contract as the production egress-bound path.
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # packages/

from source_adapters import (  # noqa: E402
    JsonCache,
    fetch_github_stars,
    fetch_google_trends_trending,
    fetch_hf_daily_papers,
    fetch_hn_stories,
    fetch_reddit_new,
)
from source_adapters.trendcache import cached_json  # noqa: E402
from source_adapters.trendcache import cached_text  # noqa: E402,F401


class FakeFetcher:
    """fetch_policy stand-in: routes canned payloads by request URL."""

    def __init__(self, routes: dict):
        # routes: url -> dict/list (served as JSON) or bytes (served raw)
        self.routes = routes
        self.calls: list = []

    def fetch_policy(self, url, *, headers=None, params=None, policy=None):
        self.calls.append((url, params))
        if url not in self.routes:
            response = httpx.Response(404, request=httpx.Request("GET", url))
            raise httpx.HTTPStatusError(f"no route for {url}", request=response.request,
                                        response=response)
        payload = self.routes[url]
        body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode()
        response = httpx.Response(200, content=body, request=httpx.Request("GET", url))
        return response


NOW = time.time()


# ------------------------------------------------------------ Hugging Face

HF_PAPERS = [
    {
        "paper": {
            "id": "2410.12345",
            "title": "Efficient Serving with PagedAttention",
            "summary": "We reduce serving cost with a paged KV cache. ",
            "upvotes": 42,
        },
        "publishedAt": "2026-10-23T08:00:00.000Z",
    },
    {"paper": None},  # malformed → skipped
    {"paper": {"id": "2410.00099", "title": "  ", "summary": None, "upvotes": "7"}},
    "not-a-dict",  # junk entries are skipped, never crash the run
]


class TestHfPapers:
    def test_maps_valid_entries_with_signal(self):
        fetcher = FakeFetcher({"https://huggingface.co/api/daily_papers": HF_PAPERS})
        items = fetch_hf_daily_papers(limit=30, fetcher=fetcher)
        assert len(items) == 2
        first = next(i for i in items if i.external_item_id == "hf-paper:2410.12345")
        assert first.url == "https://huggingface.co/papers/2410.12345"
        assert first.title == "[Paper] Efficient Serving with PagedAttention"
        assert "42 community upvotes" in first.text
        assert first.published_at is not None

    def test_ids_are_stable_for_dedup(self):
        fetcher = FakeFetcher({"https://huggingface.co/api/daily_papers": HF_PAPERS})
        again = fetch_hf_daily_papers(limit=30, fetcher=fetcher)
        assert {i.external_item_id for i in again} == {
            "hf-paper:2410.12345", "hf-paper:2410.00099",
        }

    def test_limits_and_date_params_are_passed(self):
        fetcher = FakeFetcher({"https://huggingface.co/api/daily_papers": []})
        fetch_hf_daily_papers("2026-10-22", limit=5, fetcher=fetcher)
        url, params = fetcher.calls[0]
        assert params["limit"] == 5
        assert params["date"] == "2026-10-22"

    def test_upvotes_survive_string_values(self):
        fetcher = FakeFetcher({"https://huggingface.co/api/daily_papers": HF_PAPERS})
        items = fetch_hf_daily_papers(fetcher=fetcher)
        with_upvotes = [i for i in items if i.external_item_id == "hf-paper:2410.00099"]
        assert len(with_upvotes) == 1
        assert "7 community upvotes" in with_upvotes[0].text

    def test_cache_prevents_refetch(self):
        fetcher = FakeFetcher({"https://huggingface.co/api/daily_papers": HF_PAPERS})
        cache = JsonCache(namespace="test", default_ttl_s=600, clock=lambda: NOW)
        first = fetch_hf_daily_papers(fetcher=fetcher, cache=cache)
        second = fetch_hf_daily_papers(fetcher=fetcher, cache=cache)
        assert len(fetcher.calls) == 1
        assert [i.external_item_id for i in first] == [i.external_item_id for i in second]

    def test_unexpected_payload_shape_raises(self):
        fetcher = FakeFetcher({"https://huggingface.co/api/daily_papers": {"oops": 1}})
        with pytest.raises(ValueError):
            fetch_hf_daily_papers(fetcher=fetcher)


# ------------------------------------------------------------- Hacker News

# Relative to "now": the adapter enforces max_age_hours against the wall
# clock, so a fixed date made this fixture expire 72 h after it was written.
_RECENT = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

HN_RESPONSE = {
    "hits": [
        {
            "objectID": "424242",
            "title": "New AI API offers free trial credits",
            "url": "https://example.com/ai-credits",
            "points": 320,
            "num_comments": 210,
            "created_at": _RECENT,
        },
        {
            "objectID": "424243",
            "title": "Old story",
            "url": None,
            "points": 500,
            "num_comments": 12,
            "created_at": "2024-01-01T00:00:00Z",  # outside max_age → dropped
        },
        {
            "objectID": "424244",
            "title": "Thin story",
            "url": "https://example.com/thin",
            "points": 3,  # below min_points → dropped
            "num_comments": 1,
            "created_at": _RECENT,
        },
        {"no_object_id": True},  # junk → skipped
    ]
}


class TestHnStories:
    def test_maps_stories_with_signals(self):
        fetcher = FakeFetcher({"https://hn.algolia.com/api/v1/search_by_date": HN_RESPONSE})
        items = fetch_hn_stories("AI", min_points=50, max_age_hours=72, fetcher=fetcher)
        assert len(items) == 1
        story = items[0]
        assert story.external_item_id == "hn:424242"
        assert story.url == "https://example.com/ai-credits"
        assert story.title == "New AI API offers free trial credits"
        assert "320 points, 210 comments" in story.text
        assert story.published_at is not None

    def test_missing_url_falls_back_to_hn_discussion(self):
        # max_age_hours=0 disables the freshness filter so the 2024 fixture
        # story reaches the mapping code.
        fetcher = FakeFetcher({"https://hn.algolia.com/api/v1/search_by_date": HN_RESPONSE})
        items = fetch_hn_stories("AI", min_points=50, max_age_hours=0, fetcher=fetcher)
        fallback = next(i for i in items if i.external_item_id == "hn:424243")
        assert fallback.url == "https://news.ycombinator.com/item?id=424243"

    def test_query_required(self):
        with pytest.raises(ValueError):
            fetch_hn_stories("  ")

    def test_numeric_filters_sent_to_api(self):
        fetcher = FakeFetcher({"https://hn.algolia.com/api/v1/search_by_date": {"hits": []}})
        fetch_hn_stories("AI", min_points=100, max_age_hours=24, limit=10, fetcher=fetcher)
        _, params = fetcher.calls[0]
        assert params["tags"] == "story"
        assert params["hitsPerPage"] == 10
        assert "points>=100" in params["numericFilters"]
        assert "created_at_i>" in params["numericFilters"]

    def test_cache_prevents_refetch(self):
        fetcher = FakeFetcher({"https://hn.algolia.com/api/v1/search_by_date": HN_RESPONSE})
        cache = JsonCache(namespace="test", default_ttl_s=600, clock=lambda: NOW)
        fetch_hn_stories("AI", fetcher=fetcher, cache=cache, max_age_hours=0)
        fetch_hn_stories("AI", fetcher=fetcher, cache=cache, max_age_hours=0)
        assert len(fetcher.calls) == 1


# ------------------------------------------------------------ GitHub stars

GH_ROUTES = {
    "https://api.github.com/repos/ollama/ollama": {
        "stargazers_count": 110000, "description": "Run LLMs locally.",
    },
    "https://api.github.com/repos/ggml-org/llama.cpp": {
        "stargazers_count": 75000, "description": "LLM inference in C/C++",
    },
}


class GHFakeFetcher:
    """Per-repo scripted httpx responses WITH real headers (G14).

    Mirrors Fetcher.fetch_policy's contract: non-2xx raises
    httpx.HTTPStatusError carrying the reconstructed response (headers
    included, per the G14 egress change).
    """

    def __init__(self, responses: dict[str, list[httpx.Response]]):
        self.responses = responses  # url -> queue of canned responses
        self.calls: list[tuple[str, dict]] = []

    def fetch_policy(self, url, *, headers=None, params=None, policy=None):
        self.calls.append((url, dict(headers or {})))
        queue = self.responses[url]
        if not queue:
            raise AssertionError(f"unexpected extra call to {url}")
        resp = queue.pop(0)
        if resp.status_code >= 400:
            request = httpx.Request("GET", url, headers=dict(headers or {}))
            raise httpx.HTTPStatusError(
                f"HTTP {resp.status_code}", request=request, response=resp)
        return resp


def _gh_response(body, status=200, headers=None):
    return httpx.Response(status, headers=headers or {},
                          content=body if isinstance(body, bytes)
                          else json.dumps(body).encode())


class TestGithubStarsAuthG14:
    def test_token_is_actually_sent_as_bearer(self):
        fetcher = GHFakeFetcher({
            "https://api.github.com/repos/ollama/ollama": [
                _gh_response({"stargazers_count": 5, "description": "x"}),
            ],
        })
        fetch_github_stars(["ollama/ollama"], fetcher=fetcher, token="ghp_test")
        url, headers = fetcher.calls[0]
        assert headers["Authorization"] == "Bearer ghp_test"

    def test_conditional_requests_304_short_circuits_and_etags_are_cached(self):
        monkey_cache = JsonCache(namespace="g14", clock=lambda: NOW)
        etag_hdrs = {"etag": 'W/"abc123"', "x-ratelimit-remaining": "4000"}
        fetcher = GHFakeFetcher({
            "https://api.github.com/repos/ollama/ollama": [
                _gh_response({"stargazers_count": 5}, headers=etag_hdrs),
                _gh_response(b"", status=304, headers=etag_hdrs),
            ],
        })
        items = fetch_github_stars(["ollama/ollama"], fetcher=fetcher,
                                   cache=monkey_cache)
        assert len(items) == 1
        assert monkey_cache.get_text("gh-stars:etag:ollama/ollama") == 'W/"abc123"'
        # Second sweep: conditional request with the stored etag, 304 → no
        # item, no full-body fetch wasted.
        items2 = fetch_github_stars(["ollama/ollama"], fetcher=fetcher,
                                    cache=monkey_cache)
        assert items2 == []
        assert len(fetcher.calls) == 2
        assert fetcher.calls[1][1].get("If-None-Match") == 'W/"abc123"'

    def test_primary_rate_limit_stops_the_run_fail_closed(self):
        fetcher = GHFakeFetcher({
            "https://api.github.com/repos/ollama/ollama": [
                _gh_response({"stargazers_count": 5},
                             headers={"x-ratelimit-remaining": "0",
                                      "x-ratelimit-reset": "1735689600"}),
            ],
            "https://api.github.com/repos/ggml-org/llama.cpp": [
                _gh_response({"stargazers_count": 6}),
            ],
        })
        with pytest.raises(RuntimeError, match="1735689600"):
            fetch_github_stars(["ollama/ollama", "ggml-org/llama.cpp"],
                               fetcher=fetcher)
        # Stopped BEFORE hammering the refused quota: only the first call.
        assert len(fetcher.calls) == 1

    def test_http_429_refusal_surfaces_retry_after(self):
        import httpx as _hx

        fetcher = GHFakeFetcher({
            "https://api.github.com/repos/ollama/ollama": [
                _gh_response(b"", status=429, headers={"retry-after": "60"}),
            ],
        })
        with pytest.raises(RuntimeError, match="retry after 60s"):
            fetch_github_stars(["ollama/ollama"], fetcher=fetcher)


class TestGithubStars:
    def test_stable_entity_id_and_star_payload(self):
        fetcher = FakeFetcher(GH_ROUTES)
        items = fetch_github_stars(["ollama/ollama"], fetcher=fetcher)
        assert items[0].external_item_id == "gh-stars:ollama/ollama"
        assert items[0].url == "https://github.com/ollama/ollama"
        assert "110000 GitHub stars" in items[0].title
        assert items[0].extra["stars"] == 110000
        assert "Signal: GitHub star snapshot" in items[0].text

    def test_count_change_keeps_the_same_story(self):
        # G08: the count is a MEASUREMENT, not identity — a star change must
        # stay one dedupable story with a second observation, not churn a
        # new item row keyed by the title count.
        low = FakeFetcher({"https://api.github.com/repos/ollama/ollama":
                           {"stargazers_count": 109999, "description": ""}})
        items_low = fetch_github_stars("ollama/ollama", fetcher=low)
        assert items_low[0].external_item_id == "gh-stars:ollama/ollama"
        assert items_low[0].extra["stars"] == 109999

    def test_accepts_single_repo_string_and_multiple(self):
        fetcher = FakeFetcher(GH_ROUTES)
        items = fetch_github_stars(["ollama/ollama", "ggml-org/llama.cpp"], fetcher=fetcher)
        assert len(items) == 2

    def test_rejects_bad_input(self):
        with pytest.raises(ValueError):
            fetch_github_stars([], fetcher=FakeFetcher({}))
        with pytest.raises(ValueError):
            fetch_github_stars(["not a repo"], fetcher=FakeFetcher({}))
        with pytest.raises(ValueError):
            fetch_github_stars([f"own/{'r' * 300}"], fetcher=FakeFetcher({}))


# ---------------------------------------------------------------- Reddit

REDDIT_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "id": "abc123",
                    "title": "Local model runs free on old laptop",
                    "selftext": "Here is how I set it up.",
                    "score": 450,
                    "num_comments": 120,
                    "permalink": "/r/LocalLLaMA/comments/abc123/x/",
                    "created_utc": NOW - 3600,
                }
            },
            {
                "data": {
                    "id": "def456",
                    "title": "Low effort thread",
                    "selftext": "",
                    "score": 10,  # below min_score → dropped
                    "num_comments": 2,
                    "permalink": "/r/LocalLLaMA/comments/def456/y/",
                    "created_utc": NOW - 600,
                }
            },
            {
                "data": {
                    "id": "ghi789",
                    "title": "Yesterday's news",
                    "selftext": "",
                    "score": 900,
                    "num_comments": 5,
                    "permalink": "/r/LocalLLaMA/comments/ghi789/z/",
                    "created_utc": NOW - 100 * 3600,  # outside max_age → dropped
                }
            },
        ]
    }
}


class TestReddit:
    def test_maps_posts_with_signals(self):
        fetcher = FakeFetcher({
            "https://www.reddit.com/r/LocalLLaMA/new.json": REDDIT_RESPONSE,
        })
        items = fetch_reddit_new("LocalLLaMA", min_score=25, max_age_hours=48, fetcher=fetcher)
        assert len(items) == 1
        post = items[0]
        assert post.external_item_id == "reddit:abc123"
        assert post.url == "https://www.reddit.com/r/LocalLLaMA/comments/abc123/x/"
        assert "450 upvotes, 120 comments" in post.text
        assert post.published_at is not None

    def test_invalid_subreddit_rejected(self):
        for bad in ("", "../etc", "a b", "/x/", "s" * 30):
            with pytest.raises(ValueError):
                fetch_reddit_new(bad, fetcher=FakeFetcher({}))

    def test_age_and_score_filters_apply(self):
        fetcher = FakeFetcher({"https://www.reddit.com/r/LocalLLaMA/new.json": REDDIT_RESPONSE})
        items = fetch_reddit_new("LocalLLaMA", min_score=0, max_age_hours=0, fetcher=fetcher)
        # No filters: all three posts pass.
        assert {i.external_item_id for i in items} == {
            "reddit:abc123", "reddit:def456", "reddit:ghi789",
        }


# ---------------------------------------------------------- Google Trends

TRENDS_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:ht="https://trends.google.com/trending/rss">
  <channel>
    <title>Trending searches</title>
    <item>
      <title>free ai api credits</title>
      <ht:approx_traffic>20000+</ht:approx_traffic>
      <ht:news_item>
        <ht:news_item_title>Provider launches credit program</ht:news_item_title>
      </ht:news_item>
    </item>
    <item>
      <title>student discount hosting</title>
      <ht:approx_traffic>50000+</ht:approx_traffic>
    </item>
    <item><title></title></item>
  </channel>
</rss>
"""


class TestGoogleTrends:
    def test_parses_rss_with_signals(self):
        fetcher = FakeFetcher({"https://trends.google.com/trending/rss": TRENDS_RSS})
        items = fetch_google_trends_trending("US", fetcher=fetcher)
        assert len(items) == 2
        first = items[0]
        assert first.title == "Trending search: free ai api credits"
        assert "Approx traffic: 20000+" in first.text
        assert "News: Provider launches credit program" in first.text
        assert "free%20ai%20api%20credits" in first.url or \
            "free+ai+api+credits" in first.url
        ids = {i.external_item_id for i in items}
        assert len(ids) == 2
        assert all(i.external_item_id.startswith("gt:US:") for i in items)

    def test_ids_stable_across_polls(self):
        fetcher = FakeFetcher({"https://trends.google.com/trending/rss": TRENDS_RSS})
        again = fetch_google_trends_trending("US", fetcher=fetcher)
        assert {i.external_item_id for i in again} == {
            i.external_item_id
            for i in fetch_google_trends_trending("US", fetcher=FakeFetcher(
                {"https://trends.google.com/trending/rss": TRENDS_RSS}))
        }

    def test_geo_param_sent(self):
        fetcher = FakeFetcher({"https://trends.google.com/trending/rss": TRENDS_RSS})
        fetch_google_trends_trending("PK", fetcher=fetcher)
        _, params = fetcher.calls[0]
        assert params == {"geo": "PK"}

    @pytest.mark.parametrize("bad", ["", "usa", "P1", "U"])
    def test_invalid_geo_rejected(self, bad):
        with pytest.raises(ValueError):
            fetch_google_trends_trending(bad, fetcher=FakeFetcher({}))

    def test_cached_parse_is_identical_to_live_parse(self, monkeypatch):
        """G10: the RSS body used to go into set_json (json.dumps on bytes →
        TypeError), so any configured cache broke every fetch. Now the exact
        text is cached and the cached parse equals the live parse item for
        item — the acceptance criterion."""
        monkeypatch.delenv("REDIS_URL", raising=False)
        cache = JsonCache(namespace="t", clock=lambda: NOW)
        fetcher = FakeFetcher({"https://trends.google.com/trending/rss": TRENDS_RSS})
        live = fetch_google_trends_trending("US", fetcher=fetcher, cache=cache)
        assert len(fetcher.calls) == 1

        cached = fetch_google_trends_trending("US", fetcher=fetcher, cache=cache)
        # Served from the cache: no second network call, identical result.
        assert len(fetcher.calls) == 1
        assert [(i.external_item_id, i.title, i.text, i.url) for i in cached] == \
            [(i.external_item_id, i.title, i.text, i.url) for i in live]
        assert cached[0].external_item_id.startswith("gt:US:")

    def test_text_cache_rejects_non_text_values(self, monkeypatch):
        """The typed text path refuses to silently json-encode bytes again."""
        monkeypatch.delenv("REDIS_URL", raising=False)
        cache = JsonCache(namespace="t", clock=lambda: NOW)
        with pytest.raises(TypeError):
            cache.set_text("k", b"<rss/>")  # type: ignore[arg-type]


# ---------------------------------------------------------------- cache

class TestJsonCache:
    def test_set_get_roundtrip_memory(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        cache = JsonCache(namespace="t", clock=lambda: NOW)
        cache.set_json("k", {"a": 1})
        assert cache.get_json("k") == {"a": 1}

    def test_ttl_expiry(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        clock = {"t": 1000.0}
        cache = JsonCache(namespace="t", default_ttl_s=10, clock=lambda: clock["t"])
        cache.set_json("k", [1, 2], ttl_s=5)
        clock["t"] += 4
        assert cache.get_json("k") == [1, 2]
        clock["t"] += 2  # past the 5 s ttl
        assert cache.get_json("k") is None

    def test_bounded_memory_eviction(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        cache = JsonCache(namespace="t", clock=lambda: NOW, max_entries=3)
        for n in range(5):
            cache.set_json(f"k{n}", n)
        assert cache.get_json("k0") is None  # evicted
        assert cache.get_json("k4") == 4     # newest survives

    def test_cached_json_never_caches_none(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        cache = JsonCache(namespace="t", clock=lambda: NOW)
        calls = {"n": 0}

        def failing_loader():
            calls["n"] += 1
            return None

        assert cached_json(cache, "k", 60, failing_loader) is None
        assert cached_json(cache, "k", 60, failing_loader) is None
        assert calls["n"] == 2  # a failed/empty load retries next sweep

    def test_redis_unreachable_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # nothing there
        cache = JsonCache(namespace="t", clock=lambda: NOW)
        cache.set_json("k", {"ok": True})  # must not raise
        assert cache.get_json("k") == {"ok": True}
