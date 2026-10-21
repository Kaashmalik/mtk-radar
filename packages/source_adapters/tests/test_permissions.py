"""Provider robots.txt permission decisions (WP01 slice 6).

A politeness delay is not permission. Coverage: the allow/deny parsing, the
fail-closed statuses, and the refusal to guess when the policy cannot be read.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # packages/

from source_adapters.egress import EgressError, FetchResult  # noqa: E402
from source_adapters.permissions import check_robots  # noqa: E402

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
ALLOW_ALL = b"User-agent: *\nAllow: /\n"
DISALLOW_ALL = b"User-agent: *\nDisallow: /\n"


class FakeFetcher:
    def __init__(self, *, status=200, body=b"", error=None):
        self.status = status
        self.body = body
        self.error = error
        self.calls = []

    def safe_fetch(self, url, *, policy=None, clock=None):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return FetchResult(
            requested_url=url, final_url=url, status=self.status,
            content_type="text/plain", body=self.body, redirects=(),
            fetched_at=NOW,
        )


def decide(*, status=200, body=b"", error=None, path="/", domain="example.com"):
    fetcher = FakeFetcher(status=status, body=body, error=error)
    decision = check_robots(domain, fetcher=fetcher, clock=lambda: NOW, path=path)
    return decision, fetcher


def test_allowed_policy_permits_the_fetch():
    decision, _ = decide(body=ALLOW_ALL)
    assert decision.allowed is True
    assert decision.status == 200
    assert decision.domain == "example.com"
    assert decision.checked_at == NOW
    assert "permits" in decision.reason


def test_disallow_all_blocks_the_fetch():
    decision, _ = decide(body=DISALLOW_ALL)
    assert decision.allowed is False
    assert decision.status == 200
    assert "disallows" in decision.reason


def test_disallow_is_path_scoped():
    robots = b"User-agent: *\nDisallow: /terms\n"
    blocked, _ = decide(body=robots, path="/terms")
    allowed, _ = decide(body=robots, path="/pricing")
    assert blocked.allowed is False
    assert allowed.allowed is True


def test_other_agents_rules_do_not_bind_us():
    robots = b"User-agent: SomeOtherBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    decision, _ = decide(body=robots)
    assert decision.allowed is True


def test_robots_txt_is_read_from_the_host_over_https():
    _, fetcher = decide(body=ALLOW_ALL)
    assert fetcher.calls == ["https://example.com/robots.txt"]


def test_missing_robots_file_means_no_published_policy():
    decision, _ = decide(status=404)
    assert decision.allowed is True
    assert decision.status == 404
    assert "no published policy" in decision.reason


def test_auth_wall_is_not_permission():
    for status in (401, 403):
        decision, _ = decide(status=status)
        assert decision.allowed is False
        assert "HTTP %s" % status in decision.reason


def test_rate_limit_is_not_permission():
    decision, _ = decide(status=429)
    assert decision.allowed is False


def test_server_error_fails_closed():
    decision, _ = decide(status=503)
    assert decision.allowed is False
    assert decision.status == 503
    assert "refusing" in decision.reason


def test_egress_policy_refusal_fails_closed():
    decision, _ = decide(error=EgressError("resolves to a private address"))
    assert decision.allowed is False
    assert decision.status is None
    assert "safely" in decision.reason


def test_transport_failure_fails_closed():
    decision, _ = decide(error=httpx.ConnectError("boom"))
    assert decision.allowed is False
    assert "unreachable" in decision.reason


def test_non_bare_host_is_never_guessed():
    decision, fetcher = decide(domain="example.com/terms")
    assert decision.allowed is False
    assert fetcher.calls == []
    assert "invalid provider host" in decision.reason


def test_provenance_shape_is_exact():
    decision, _ = decide(body=ALLOW_ALL)
    assert decision.as_provenance() == {
        "robots_url": "https://example.com/robots.txt",
        "checked_at": "2026-10-21T12:00:00+00:00",
        "allowed": True,
        "status": 200,
    }
