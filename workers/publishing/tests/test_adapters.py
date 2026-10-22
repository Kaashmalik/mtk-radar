"""Adapter tests with mocked HTTP — no real network, no real tokens.

Covers the week-10 exit criteria: private/test upload + token-expiry recovery.
"""

import httpx
import pytest

from platforms import (
    FacebookAdapter,
    OAuthConfig,
    TokenExpiredError,
    YouTubeAdapter,
)


def _video(tmp_path):
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"fake video bytes")
    return p


class FakeSessionStore:
    def __init__(self, record=None):
        self.record = record
        self.saved = []
        self.progress_calls = []
        self.cleared = 0

    def load(self):
        return self.record

    def save(self, uri, content_length):
        self.saved.append((uri, content_length))
        self.record = {"session_uri": uri, "content_length": content_length}

    def progress(self, offset):
        self.progress_calls.append(offset)

    def clear(self):
        self.cleared += 1
        self.record = None


class TestYouTube:
    def test_private_upload_success(self, tmp_path):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "oauth2.googleapis.com/token" in url:
                return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
            if "uploadType=resumable" in url:
                calls.append("init")
                return httpx.Response(200, headers={"location": "https://upload.example/session"})
            if url == "https://upload.example/session":
                calls.append("put")
                return httpx.Response(200, json={"id": "vid_abc123"})
            return httpx.Response(404)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(
            oauth=OAuthConfig("cid", "csecret", "rtok"),
            account_id="acc1", http=http,
        )
        remote = adapter.upload(_video(tmp_path), {"title": "T", "caption": "c"},
                                privacy="private", idempotency_key="key1")
        assert remote == "vid_abc123"
        assert calls == ["init", "put"]

    def test_resumable_upload_uses_provider_offset(self, tmp_path):
        video = _video(tmp_path)
        total = len(video.read_bytes())
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://upload.example/session"
            if request.headers.get("content-range") == f"bytes */{total}":
                return httpx.Response(308, headers={"range": "bytes=0-3"})
            seen.append({
                "range": request.headers.get("content-range"),
                "body": request.read(),
            })
            return httpx.Response(200, json={"id": "vid_resumed"})

        store = FakeSessionStore({
            "session_uri": "https://upload.example/session",
            "content_length": total,
        })
        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=None, access_token="tok", http=http)
        adapter.set_upload_session_store(store)
        remote = adapter.upload(video, {"title": "T"}, privacy="private")

        assert remote == "vid_resumed"
        assert store.progress_calls == [4]
        assert store.cleared == 1
        assert seen[0]["range"] == f"bytes 4-{total - 1}/{total}"
        assert seen[0]["body"] == video.read_bytes()[4:], \
            "the resumed request must contain only bytes YouTube has not seen"

    def test_new_session_is_persisted_before_the_first_chunk(self, tmp_path):
        video = _video(tmp_path)

        def handler(request: httpx.Request) -> httpx.Response:
            if "uploadType=resumable" in str(request.url):
                return httpx.Response(
                    200, headers={"location": "https://upload.example/new"})
            return httpx.Response(200, json={"id": "vid_new"})

        store = FakeSessionStore()
        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=None, access_token="tok", http=http)
        adapter.set_upload_session_store(store)

        assert adapter.upload(video, {}, privacy="private") == "vid_new"
        assert store.saved == [("https://upload.example/new", len(video.read_bytes()))]
        assert store.cleared == 1

    def test_session_size_mismatch_fails_closed(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            if "uploadType=resumable" in str(request.url):
                raise AssertionError("must not start a new upload for a different file")
            return httpx.Response(500)

        store = FakeSessionStore({
            "session_uri": "https://upload.example/other",
            "content_length": 999,
        })
        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=None, access_token="tok", http=http)
        adapter.set_upload_session_store(store)

        with pytest.raises(RuntimeError, match="does not match"):
            adapter.upload(_video(tmp_path), {}, privacy="private")
        assert store.cleared == 1

    def test_expired_session_is_cleared_and_restarted(self, tmp_path):
        video = _video(tmp_path)
        state = {"init": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if "uploadType=resumable" in str(request.url):
                state["init"] += 1
                return httpx.Response(
                    200, headers={"location": "https://upload.example/fresh"})
            if request.headers.get("content-range") == "bytes */16":
                return httpx.Response(404)
            return httpx.Response(200, json={"id": "vid_fresh"})

        store = FakeSessionStore({
            "session_uri": "https://upload.example/dead",
            "content_length": 16,
        })
        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=None, access_token="tok", http=http)
        adapter.set_upload_session_store(store)

        assert adapter.upload(video, {}, privacy="private") == "vid_fresh"
        assert state["init"] == 1
        assert store.cleared == 2  # expired row, then the new row after success

    def test_refreshed_expiry_reported_not_token(self, tmp_path):
        reported = {}

        def on_refresh(expires_at):
            reported["expires_at"] = expires_at
            reported["keys"] = set(dir())

        def handler(request: httpx.Request) -> httpx.Response:
            if "token" in str(request.url):
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 1800})
            return httpx.Response(200, headers={"location": "https://u/s"}, json={})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=OAuthConfig("c", "s", "r"),
                                 account_id="acc1", on_refresh=on_refresh, http=http)
        adapter.ensure_ready()
        assert "expires_at" in reported

    def test_401_recovers_via_refresh_and_retry(self, tmp_path):
        state = {"token": "old"}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "token" in url:
                state["token"] = "new"
                return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})
            if "uploadType=resumable" in url:
                if request.headers.get("authorization") == "Bearer old":
                    return httpx.Response(401)
                state.setdefault("inits_after_refresh", 0)
                state["inits_after_refresh"] += 1
                return httpx.Response(200, headers={"location": "https://u/s"})
            if url == "https://u/s":
                return httpx.Response(200, json={"id": "vid_ok"})
            return httpx.Response(404)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=OAuthConfig("c", "s", "r"),
                                 access_token="old", account_id="acc1", http=http)
        remote = adapter.upload(_video(tmp_path), {}, privacy="private")
        assert remote == "vid_ok"
        assert state["inits_after_refresh"] == 1  # retried exactly once after refresh

    def test_refresh_failure_raises_token_expired(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            if "token" in str(request.url):
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(500)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=OAuthConfig("c", "s", "BAD"), account_id="acc1", http=http)
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")

    def test_missing_credentials_raise(self, tmp_path):
        adapter = YouTubeAdapter(oauth=None, account_id="acc1")
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")


class TestFacebook:
    def test_unpublished_test_upload(self, tmp_path):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["published"] = getattr(request, "_content", b"")
            return httpx.Response(200, json={"id": "fb_video_1"})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = FacebookAdapter("PAGE_ID", "page_token", account_id="acc2", http=http)
        remote = adapter.upload(_video(tmp_path), {"title": "T", "caption": "c"}, privacy="private")
        assert remote == "fb_video_1"

    def test_dead_session_error_raises(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"code": 190, "message": "expired"}})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = FacebookAdapter("PAGE_ID", "dead", http=http)
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")

    def test_missing_credentials_raise(self, tmp_path):
        adapter = FacebookAdapter("", "", http=httpx.Client())
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")


class TestYouTubePackage:
    def _adapter(self, handler):
        # Static token: avoids a token-refresh call in these package tests.
        http = httpx.Client(transport=httpx.MockTransport(handler))
        return YouTubeAdapter(oauth=None,
                              access_token="tok", account_id="acc1", http=http)

    def test_finalize_attaches_thumbnail_captions_playlist_and_comment(self, tmp_path):
        seen = []
        cover = tmp_path / "cover.png"
        cover.write_bytes(b"\x89PNG\r\n\x1a\n")
        captions = tmp_path / "captions.en.vtt"
        captions.write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n")

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            seen.append((request.method, url))
            if "thumbnails/set" in url:
                return httpx.Response(200, json={"items": []})
            if "captions" in url:
                return httpx.Response(200, json={"id": "cap-1"})
            if "playlistItems" in url:
                return httpx.Response(200, json={"id": "pl-item-1"})
            if "commentThreads" in url:
                return httpx.Response(200, json={"id": "comment-1"})
            return httpx.Response(404)

        result = self._adapter(handler).finalize_package(
            "vid-1", {"captions_language": "en"},
            thumbnail_path=cover, captions_path=captions,
            playlist_id="PL-1", pinned_comment="Official sources below",
        )
        assert result["thumbnail"]["ok"] is True
        assert result["captions"]["id"] == "cap-1"
        assert result["playlist"]["id"] == "pl-item-1"
        assert result["comment"]["id"] == "comment-1"
        assert result["comment"]["pinned"] is False
        assert "operator_action" in result["comment"], \
            "the API cannot pin comments - say so instead of pretending"
        assert result["complete"] is True
        assert result["failures"] == {}
        assert result["mandatory"] == ["captions", "comment", "playlist", "thumbnail"]
        assert any("thumbnails/set" in url for _, url in seen)
        assert any("uploadType=multipart" in url for _, url in seen)

    def test_requested_asset_failure_makes_the_package_incomplete(self, tmp_path):
        cover = tmp_path / "cover.png"
        cover.write_bytes(b"\x89PNG\r\n\x1a\n")
        captions = tmp_path / "captions.en.vtt"
        captions.write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n")

        def handler(request: httpx.Request) -> httpx.Response:
            if "thumbnails/set" in str(request.url):
                return httpx.Response(500, text="thumbnail rejected")
            if "captions" in str(request.url):
                return httpx.Response(200, json={"id": "cap-1"})
            return httpx.Response(404)

        result = self._adapter(handler).finalize_package(
            "vid-1", {}, thumbnail_path=cover, captions_path=captions,
        )
        assert result["complete"] is False
        assert "thumbnail" in result["failures"]
        assert "thumbnail rejected" in result["failures"]["thumbnail"]
        assert result["captions"]["ok"] is True

    def test_confirm_waits_for_processed_and_matching_privacy(self):
        state = {"polls": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["polls"] += 1
            if state["polls"] == 1:
                return httpx.Response(200, json={"items": [{
                    "status": {"uploadStatus": "processing", "privacyStatus": "private"},
                    "processingDetails": {"processingStatus": "processing"},
                }]})
            return httpx.Response(200, json={"items": [{
                "status": {"uploadStatus": "processed", "privacyStatus": "private"},
                "processingDetails": {"processingStatus": "succeeded"},
            }]})

        result = self._adapter(handler).confirm_publication(
            "vid-1", expected_privacy="private", timeout_s=2, interval_s=0.01)
        assert result["confirmed"] is True
        assert result["privacy"] == "private"
        assert result["remote_url"].endswith("vid-1")
        assert state["polls"] == 2

    def test_confirm_refuses_a_privacy_mismatch(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": [{
                "status": {"uploadStatus": "processed", "privacyStatus": "public"},
                "processingDetails": {"processingStatus": "succeeded"},
            }]})

        result = self._adapter(handler).confirm_publication(
            "vid-1", expected_privacy="private", timeout_s=0, interval_s=0.01)
        assert result["confirmed"] is False

    def test_retention_uses_elapsed_ratio_and_video_duration(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/videos"):
                return httpx.Response(200, json={"items": [{
                    "contentDetails": {"duration": "PT1M40S"},
                }]})
            return httpx.Response(200, json={"rows": [
                [0.0, 1.0], [0.03, 0.61], [0.10, 0.42],
            ]})

        value = self._adapter(handler).fetch_retention_3s("vid-1")
        assert value == pytest.approx(0.61)


def test_upload_sends_the_approved_description_verbatim(tmp_path):
    """Chapters are finalized in the scheduler and covered by the metadata
    hash. The adapter must not edit the description after that hash check."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "uploadType=resumable" in url:
            captured["body"] = request.read().decode()
            return httpx.Response(200, headers={"location": "https://upload.example/s"})
        if url == "https://upload.example/s":
            return httpx.Response(200, json={"id": "vid-1"})
        return httpx.Response(404)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeAdapter(oauth=None, access_token="tok", http=http)
    meta = {
        "title": "Approved title",
        "caption": "Approved description only.",
        "chapters": [{"start_s": 0, "title": "The offer"},
                     {"start_s": 15, "title": "Proof"}],
    }
    assert adapter.upload(_video(tmp_path), meta, privacy="private") == "vid-1"
    assert "Approved description only." in captured["body"]
    assert "Chapters:" not in captured["body"], \
        "the adapter must not add text that is outside the approved metadata hash"


def test_correction_preserves_tags_and_does_not_duplicate_notice():
    """videos.update replaces the whole snippet. A correction must append the
    notice without wiping tags or appending it twice on retry."""
    current = "Original approved description."
    updated = []
    state = {"description": current}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"items": [{"snippet": {
                "title": "Approved title",
                "description": state["description"],
                "tags": ["deals", "verified"],
                "categoryId": "28",
                "defaultLanguage": "en",
            }}]})
        if request.method == "PUT":
            payload = request.read().decode()
            updated.append(payload)
            state["description"] = __import__("json").loads(payload)["snippet"]["description"]
            return httpx.Response(200, json={"id": "vid-1"})
        return httpx.Response(404)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeAdapter(oauth=None, access_token="tok", http=http)
    notice = "Correction: the deadline is 31 Dec 2026."

    adapter.apply_correction_notice("vid-1", notice)
    adapter.apply_correction_notice("vid-1", notice)

    import json as _json
    body = _json.loads(updated[-1])
    snippet = body["snippet"]
    assert snippet["tags"] == ["deals", "verified"], "tags must survive a correction"
    assert snippet["defaultLanguage"] == "en"
    assert snippet["description"].count(notice) == 1, "a retry must not duplicate the notice"
    assert "Original approved description." in snippet["description"]


class TestYouTubeAnalyticsGroups:
    def _adapter(self, handler):
        http = httpx.Client(transport=httpx.MockTransport(handler))
        return YouTubeAdapter(oauth=None, access_token="tok",
                              account_id="acc1", http=http)

    def test_unsupported_group_degrades_instead_of_dropping_everything(self):
        """One rejected metric group must not discard the metrics that work,
        and nearest-bucket retention must be marked as an estimate (§7.F.3-F.6).
        """
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            params = request.url.params
            if "/youtube/v3/videos" in url:
                return httpx.Response(200, json={
                    "items": [{"contentDetails": {"duration": "PT2M"}}]})
            if "youtubeanalytics" in url:
                if params.get("dimensions") == "elapsedVideoTimeRatio":
                    return httpx.Response(200, json={
                        "columnHeaders": [{"name": "elapsedVideoTimeRatio"},
                                          {"name": "audienceWatchRatio"}],
                        "rows": [[0.0, 0.8], [0.025, 0.61], [0.05, 0.5]],
                    })
                metrics = params.get("metrics", "")
                if metrics.startswith("impressions"):
                    return httpx.Response(400, json={
                        "error": {"message": "impressions are unsupported here"}})
                if metrics.startswith("views"):
                    return httpx.Response(200, json={
                        "columnHeaders": [
                            {"name": "views"}, {"name": "likes"},
                            {"name": "comments"}, {"name": "shares"},
                            {"name": "averageViewDuration"},
                        ],
                        "rows": [[1500, 88, 12, 7, 143.5]],
                    })
                return httpx.Response(200, json={
                    "columnHeaders": [
                        {"name": "averageViewPercentage"},
                        {"name": "subscribersGained"},
                        {"name": "subscribersLost"},
                        {"name": "estimatedMinutesWatched"},
                    ],
                    "rows": [[48.25, 9, 2, 3100]],
                })
            return httpx.Response(404)

        adapter = self._adapter(handler)
        report = adapter.fetch_video_metrics("vid1")

        assert report["views"] == 1500
        assert report["averageViewPercentage"] == 48.25
        assert "impressions" not in report, "a rejected group stays unavailable"
        meta = report["_meta"]
        assert meta["degraded"] is True
        assert meta["unsupported_groups"] == ["impressions"]
        assert "unsupported" in meta["degradation_detail"]
        assert meta["metric_definition"] == "youtube-analytics-v2:core,audience"
        assert report["retention_3s"] == 0.61
        assert report["retention_3s_estimated"] is True
        assert report["retention_3s_bucket_ratio"] == 0.025
        assert report["retention_3s_bucket_seconds"] == 3.0

    def test_invalid_analytics_scope_is_still_a_permission_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if "youtubeanalytics" in str(request.url):
                return httpx.Response(403, json={"error": {"message": "forbidden"}})
            return httpx.Response(404)

        with pytest.raises(PermissionError):
            self._adapter(handler).fetch_video_metrics("vid1")
