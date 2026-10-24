"""WP-G token lifecycle (§5.6.1): the ~45-day long-lived-token exchange for
Facebook/Instagram. Success reports the new expiry; refusal marks the account
expired so Needs-You shows it — never a silent stall.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # workers/publishing

import main as pub  # noqa: E402


class FakeAPI:
    def __init__(self, accounts):
        self.accounts = accounts
        self.posts: list[tuple[str, dict]] = []

    def get(self, path, params=None):
        accounts = self.accounts

        class R:
            status_code = 200

            def json(self):
                return accounts
        return R()

    def post(self, path, json=None):
        self.posts.append((path, json))

        class R:
            status_code = 200
        return R()


ACCOUNT = {
    "id": "acc-1", "platform": "facebook",
    "credential_source": "env:FACEBOOK_MAIN_",
    "status": "active", "expires_at": None, "last_refreshed_at": None,
    "created_at": None,
}


def test_token_due_uses_margin_and_cadence():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    worker = pub.Publisher.__new__(pub.Publisher)
    # expires in 10 days (< 14-day margin) → due
    due_soon = {**ACCOUNT, "expires_at": (now + timedelta(days=10)).isoformat()}
    assert worker._token_due(due_soon, now) is True
    # expires in 40 days → not due
    due_late = {**ACCOUNT, "expires_at": (now + timedelta(days=40)).isoformat()}
    assert worker._token_due(due_late, now) is False
    # no expiry, refreshed 46 days ago (> 45-day cadence) → due
    stale = {**ACCOUNT,
             "last_refreshed_at": (now - timedelta(days=46)).isoformat()}
    assert worker._token_due(stale, now) is True
    # no expiry, refreshed 5 days ago → not due
    fresh = {**ACCOUNT, "last_refreshed_at": (now - timedelta(days=5)).isoformat()}
    assert worker._token_due(fresh, now) is False
    # nothing recorded at all → due immediately
    assert worker._token_due({**ACCOUNT, "created_at": None}, now) is True


def test_successful_exchange_reports_the_new_expiry(monkeypatch):
    monkeypatch.setenv("FACEBOOK_MAIN_PAGE_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("FACEBOOK_MAIN_APP_ID", "app-1")
    monkeypatch.setenv("FACEBOOK_MAIN_APP_SECRET", "sec")
    new_expiry = datetime(2026, 3, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(pub, "_facebook_exchange",
                        lambda token, app_id, secret: {
                            "access_token": "new-tok", "expires_at": new_expiry})
    api = FakeAPI([ACCOUNT])
    worker = pub.Publisher.__new__(pub.Publisher)
    worker.api = api
    assert worker._refresh_account(ACCOUNT) is True
    (path, body), = api.posts
    assert path.endswith("/platform-accounts/acc-1/refreshed")
    assert "2026-03-01" in body["expires_at"]
    assert "tok" not in json.dumps(body), "the token itself never reaches the API"


def test_refused_exchange_marks_the_account_expired(monkeypatch):
    monkeypatch.setenv("FACEBOOK_MAIN_PAGE_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("FACEBOOK_MAIN_APP_ID", "app-1")
    monkeypatch.setenv("FACEBOOK_MAIN_APP_SECRET", "sec")

    def refused(token, app_id, secret):
        from platforms import TokenExpiredError
        raise TokenExpiredError("token exchange refused (400)")

    monkeypatch.setattr(pub, "_facebook_exchange", refused)
    api = FakeAPI([ACCOUNT])
    worker = pub.Publisher.__new__(pub.Publisher)
    worker.api = api
    assert worker._refresh_account(ACCOUNT) is False
    (path, body), = api.posts
    assert path.endswith("/platform-accounts/acc-1/mark-expired")
    assert "refused" in body["detail"]


def test_maintenance_skips_accounts_without_app_credentials(monkeypatch):
    monkeypatch.delenv("FACEBOOK_MAIN_APP_ID", raising=False)
    monkeypatch.delenv("FACEBOOK_MAIN_APP_SECRET", raising=False)
    monkeypatch.setenv("FACEBOOK_MAIN_PAGE_ACCESS_TOKEN", "tok")
    api = FakeAPI([ACCOUNT])
    worker = pub.Publisher.__new__(pub.Publisher)
    worker.api = api
    assert worker._refresh_account(ACCOUNT) is False
    assert api.posts == [], "no mark-expired: mis-configuration is not a dead token"


def test_maintenance_runs_at_most_once_per_account_per_day(monkeypatch):
    monkeypatch.setenv("FACEBOOK_MAIN_PAGE_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("FACEBOOK_MAIN_APP_ID", "a")
    monkeypatch.setenv("FACEBOOK_MAIN_APP_SECRET", "s")
    monkeypatch.setattr(pub, "_facebook_exchange",
                        lambda t, a, s: {"access_token": "nt", "expires_at": None})
    api = FakeAPI([{**ACCOUNT, "created_at": "2025-01-01T00:00:00+00:00"}])
    worker = pub.Publisher.__new__(pub.Publisher)
    worker.api = api
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert worker.token_maintenance(now) == 1
    assert worker.token_maintenance(now) == 0, "same sweep cycle: no second attempt"
