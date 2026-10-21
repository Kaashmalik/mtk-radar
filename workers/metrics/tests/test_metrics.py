"""Audience-metrics ingestion (v0.18, §7): parsers handle real provider
payload shapes; the worker measures every published post once per platform
adapter, upserts one daily snapshot, and treats missing scopes / dead tokens /
no-data-yet as skips — never as lost posts."""

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# importlib: `main` is a shared module name across worker dirs — a bare
# `import main` here would collide with the publishing worker's module cache.
_spec = importlib.util.spec_from_file_location(
    "mtk_metrics_main", Path(__file__).resolve().parent.parent / "main.py")
metrics_main = importlib.util.module_from_spec(_spec)
sys.modules["mtk_metrics_main"] = metrics_main
_spec.loader.exec_module(metrics_main)

from platform_metrics import parse_graph_insights, parse_youtube_analytics


# ------------------------------------------------------------------ parsers

def test_youtube_report_columns_map_to_snapshot():
    payload = {
        "columnHeaders": [
            {"name": "views"}, {"name": "likes"}, {"name": "comments"},
            {"name": "shares"}, {"name": "averageViewDuration"},
        ],
        "rows": [[1500, 88, 12, 7, 143.5]],
    }
    snap = parse_youtube_analytics(payload)
    assert snap["views"] == 1500 and snap["likes"] == 88 and snap["comments"] == 12
    assert snap["avg_watch_s"] == 143.5
    assert snap["impressions"] is None, "not pulled — must stay unknown, not zero"


def test_youtube_report_without_rows_is_no_data():
    with pytest.raises(ValueError):
        parse_youtube_analytics({"columnHeaders": [{"name": "views"}], "rows": []})


def test_graph_insights_entries_flatten():
    payload = {"data": [
        {"name": "total_video_views", "values": [{"value": 402}]},
        {"name": "total_video_reactions", "values": [{"value": "31"}]},
        {"name": "total_comments", "values": [{"value": 4}]},
    ]}
    snap = parse_graph_insights(payload)
    assert snap == {"views": 402, "likes": 31, "comments": 4,
                    "impressions": None, "avg_watch_s": None}


# ------------------------------------------------------------- orchestration


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAPI:
    def __init__(self, posts):
        self.posts = posts
        self.written = []

    def get(self, path, params=None):
        assert params.get("state") == "published"
        return FakeResponse(self.posts)

    def post(self, path, json=None):
        self.written.append((path, json))
        return FakeResponse({"ok": True}, status_code=201)


class FakeYouTube:
    def fetch_video_metrics(self, video_id):
        return {"views": 10, "likes": 2, "comments": 1, "shares": 0,
                "averageViewDuration": 95.0}


class FakeFacebook:
    def insights(self, video_id):
        return {"total_video_views": 55, "total_video_reactions": 6, "total_comments": 2}


class NoScopeYouTube:
    def fetch_video_metrics(self, video_id):
        raise PermissionError("yt-analytics scope not granted for this OAuth client")


def _worker(posts, adapters):
    return metrics_main.MetricsWorker(adapters=adapters, api_url="http://fake")


def test_measures_every_capable_published_post():
    posts = [
        {"id": "sch-yt", "platform": "youtube", "remote_post_id": "vid1"},
        {"id": "sch-fb", "platform": "facebook", "remote_post_id": "vid2"},
        {"id": "sch-no-id", "platform": "youtube", "remote_post_id": None},
    ]
    api = FakeAPI(posts)
    w = _worker(posts, {"youtube": FakeYouTube(), "facebook": FakeFacebook()})
    w.api = api
    assert w.run_once() == 2
    by_path = {path: body for path, body in api.written}
    yt = by_path["/schedules/sch-yt/metrics"]
    assert yt["platform"] == "youtube" and yt["source"] == "youtube-analytics"
    assert yt["views"] == 10 and yt["avg_watch_s"] == 95.0
    fb = by_path["/schedules/sch-fb/metrics"]
    assert fb["source"] == "graph-insights" and fb["views"] == 55


def test_tiktok_is_a_documented_skip():
    posts = [{"id": "sch-tt", "platform": "tiktok", "remote_post_id": "tt1"}]
    w = _worker(posts, {})
    w.api = FakeAPI(posts)
    assert w.run_once() == 0, "no insights access — skip, never crash"


def test_missing_scope_skips_without_taking_the_run_down():
    posts = [{"id": "sch-yt", "platform": "youtube", "remote_post_id": "vid1"}]
    w = _worker(posts, {"youtube": NoScopeYouTube()})
    w.api = FakeAPI(posts)
    assert w.run_once() == 0


def test_unconfigured_platform_is_a_skip_not_an_error():
    posts = [{"id": "sch-ig", "platform": "instagram", "remote_post_id": "ig1"},
             {"id": "sch-fb", "platform": "facebook", "remote_post_id": "vid2"}]
    w = _worker(posts, {})  # no adapters configured at all
    w.api = FakeAPI(posts)
    assert w.run_once() == 0


def test_api_unreachable_sweep_is_nonfatal():
    class DeadAPI:
        def get(self, path, params=None):
            raise httpx.ConnectError("api down")

    w = _worker([], {})
    w.api = DeadAPI()
    assert w.run_once() == 0
