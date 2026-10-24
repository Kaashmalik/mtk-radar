from .client import Fetcher
from .egress import EgressError, EgressPolicy, FetchResult, safe_fetch
from .github_releases import fetch_github_releases
from .github_stars import fetch_github_stars
from .google_trends import fetch_google_trends_trending
from .hf_papers import fetch_hf_daily_papers
from .hn_algolia import fetch_hn_stories
from .models import RawItem
from .page_watch import PARSER_VERSION, fetch_page_snapshot
from .permissions import RobotsDecision, check_robots
from .reddit_new import fetch_reddit_new
from .registry import ADAPTERS, ADAPTER_KINDS, AdapterSpec
from .rss import fetch_rss
from .trendcache import JsonCache, cached_json

__all__ = [
    "EgressError",
    "EgressPolicy",
    "FetchResult",
    "Fetcher",
    "JsonCache",
    "PARSER_VERSION",
    "ADAPTERS",
    "ADAPTER_KINDS",
    "AdapterSpec",
    "RawItem",
    "RobotsDecision",
    "cached_json",
    "check_robots",
    "fetch_rss",
    "fetch_github_releases",
    "fetch_github_stars",
    "fetch_google_trends_trending",
    "fetch_hf_daily_papers",
    "fetch_hn_stories",
    "fetch_page_snapshot",
    "fetch_reddit_new",
    "safe_fetch",
]
