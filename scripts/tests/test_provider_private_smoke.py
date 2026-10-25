"""Fail-closed behavior of the private/test publishing smoke harness."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import provider_private_smoke as smoke  # noqa: E402
from platforms import NotConfiguredError  # noqa: E402


class FakeAdapter:
    """Stands in for a real provider adapter - no network, no tokens."""

    platform = "fake"

    def __init__(self, *, confirmed=True, confirmation=None, upload_error=None):
        self.confirmed = confirmed
        self.confirmation = confirmation
        self.upload_error = upload_error
        self.ensure_calls = 0
        self.upload_calls = []
        self.confirm_calls = []

    def ensure_ready(self):
        self.ensure_calls += 1

    def upload(self, video_path, meta, privacy="private", idempotency_key=None):
        self.upload_calls.append((Path(video_path), meta, privacy))
        if self.upload_error:
            raise self.upload_error
        return "remote-1"

    def confirm_publication(self, remote_id, *, expected_privacy, timeout_s, interval_s):
        self.confirm_calls.append((remote_id, expected_privacy, timeout_s, interval_s))
        if self.confirmation is not None:
            return self.confirmation
        return {
            "confirmed": self.confirmed,
            "processing_state": "processed",
            "remote_url": "https://example.test/private/1",
        }


def _video(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"private-smoke-video-bytes")
    return path


def test_dry_run_never_uploads_or_confirms(tmp_path):
    fake = FakeAdapter()
    evidence = smoke.run_smoke(
        providers=["youtube"], live=False, video=None,
        adapter_factory=lambda provider: fake,
    )
    assert evidence["ok"] is True
    assert evidence["mode"] == "dry-run"
    assert evidence["proof"] == "dry_run_only"
    assert evidence["providers"]["youtube"]["status"] == "ready"
    assert fake.ensure_calls == 0
    assert fake.upload_calls == []
    assert fake.confirm_calls == []


def test_instagram_is_unsupported_and_never_calls_an_adapter():
    def factory(provider):
        raise AssertionError("Instagram must not construct/use an adapter")

    result = smoke.run_provider(
        "instagram", live=True, video=Path("unused.mp4"),
        timeout_s=0, interval_s=0, adapter_factory=factory,
    )
    assert result["status"] == "unsupported_private"
    assert "no per-post private" in result["error"]


def test_missing_credentials_are_not_faked_as_a_pass():
    def factory(provider):
        raise NotConfiguredError("TikTok credentials missing (TIKTOK_REFRESH_TOKEN)")

    result = smoke.run_provider(
        "tiktok", live=True, video=Path("unused.mp4"),
        timeout_s=0, interval_s=0, adapter_factory=factory,
    )
    assert result["status"] == "not_configured"
    assert result["credentials_configured"] is False


def test_live_confirmed_private_post_records_evidence(tmp_path):
    fake = FakeAdapter(confirmation={
        "confirmed": True,
        "processing_state": "processed",
        "privacy_status": "private",
        "remote_url": "https://example.test/private/1",
    })
    video = _video(tmp_path)
    evidence = smoke.run_smoke(
        providers=["youtube"], live=True, video=video,
        timeout_s=12, interval_s=0.5,
        adapter_factory=lambda provider: fake,
    )
    assert evidence["ok"] is True
    assert evidence["proof"] == "live_private_posts_confirmed"
    result = evidence["providers"]["youtube"]
    assert result["status"] == "confirmed"
    assert result["requested_privacy"] == "private"
    assert result["remote_id"] == "remote-1"
    assert result["remote_url"] == "https://example.test/private/1"
    assert evidence["video"]["sha256"]
    assert fake.ensure_calls == 1
    assert fake.upload_calls[0][2] == "private"
    assert fake.confirm_calls[0][1] == "private"


def test_live_held_result_is_never_reported_as_success(tmp_path):
    fake = FakeAdapter(confirmation={
        "confirmed": False,
        "error": "still processing; verify manually",
    })
    evidence = smoke.run_smoke(
        providers=["facebook"], live=True, video=_video(tmp_path),
        adapter_factory=lambda provider: fake,
    )
    assert evidence["ok"] is False
    assert evidence["proof"] == "not_proven"
    assert evidence["providers"]["facebook"]["status"] == "held_unconfirmed"


def test_tokens_are_redacted_from_errors_and_confirmations(monkeypatch, tmp_path):
    secret = "super-secret-page-token-123"
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", secret)
    fake = FakeAdapter(
        confirmation={"confirmed": False, "error": f"bad {secret}"},
    )
    evidence = smoke.run_smoke(
        providers=["facebook"], live=True, video=_video(tmp_path),
        adapter_factory=lambda provider: fake,
    )
    payload = json.dumps(evidence)
    assert secret not in payload
    assert "[REDACTED]" in payload


def test_access_token_query_strings_are_redacted():
    redacted = smoke._redact(
        "https://graph.example/video?access_token=abc123&fields=id")
    assert "abc123" not in redacted
    assert "access_token=[REDACTED]" in redacted


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        smoke._parse_providers("youtube,friendster")


def test_all_expands_to_every_known_provider():
    assert smoke._parse_providers("all") == list(smoke.PROVIDERS)
