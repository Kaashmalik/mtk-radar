"""Auto-retry with exponential backoff (v0.17, §17) — the publishing worker
must requeue failed posts after base × 2^attempts seconds, cap out at
MAX_RETRIES, and leave refused transitions (e.g. hash changed → 409) for
human review instead of silently retrying forever.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as pub


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAPI:
    def __init__(self, failed_posts, transition_status=200):
        self.failed_posts = failed_posts
        self.transition_status = transition_status
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        if params and params.get("state") == "failed":
            return FakeResponse(self.failed_posts)
        return FakeResponse([])

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        return FakeResponse({"id": "x"}, status_code=self.transition_status)


def _failed(schedule_id="sch-1", retry_count=1, updated_min_ago=60):
    return {
        "id": schedule_id,
        "platform": "youtube",
        "retry_count": retry_count,
        "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=updated_min_ago)).isoformat(),
    }


def _worker(failed_posts, transition_status=200):
    p = pub.Publisher(api_url="http://fake")
    p.api = FakeAPI(failed_posts, transition_status)
    return p


def test_backoff_delays_retry_within_window():
    p = _worker([_failed(updated_min_ago=2)])  # retry_count 1 → wait 600s
    p.RETRY_BASE_S = 300
    assert p.retry_failed() == 0
    assert not [c for c in p.api.calls if c[0] == "POST"], "backoff must hold the post"


def test_backoff_elapsed_requeues_with_exponential_delay():
    p = _worker([_failed(retry_count=0, updated_min_ago=6)])
    p.RETRY_BASE_S = 300
    assert p.retry_failed() == 1
    posts = [c for c in p.api.calls if c[0] == "POST"]
    assert posts[0][2]["to"] == "scheduled"
    assert "auto-retry 1/3" in posts[0][2]["note"]


def test_max_retries_is_terminal_for_the_worker():
    p = _worker([_failed(retry_count=3, updated_min_ago=600)])
    assert p.retry_failed() == 0
    assert not [c for c in p.api.calls if c[0] == "POST"], "cap must stop auto-retry"


def test_refused_transition_stays_failed_for_operator():
    p = _worker([_failed(retry_count=0, updated_min_ago=6)], transition_status=409)
    assert p.retry_failed() == 0
    assert len([c for c in p.api.calls if c[0] == "POST"]) == 1, "attempt was made"


def test_api_unreachable_is_nonfatal():
    import httpx

    class DeadAPI:
        def get(self, path, params=None):
            raise httpx.ConnectError("api down")

    p = pub.Publisher(api_url="http://fake")
    p.api = DeadAPI()
    assert p.retry_failed() == 0
