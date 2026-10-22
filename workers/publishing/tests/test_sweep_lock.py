"""Worker locks (v0.22): two publishers must never work the same queue.

The API side: a lock is taken if it is free or expired, refused while a live
holder has it, and released explicitly. The worker side: a refused lock
skips the sweep (the other instance is doing the work), while an
UNREACHABLE lock endpoint must fail CLOSED — without proof of exclusivity a
second uploader could publish the same post twice.
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "mtk_publishing_main", Path(__file__).resolve().parent.parent / "main.py")
pub = importlib.util.module_from_spec(_spec)
sys.modules["mtk_publishing_main"] = pub
_spec.loader.exec_module(pub)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class LockingAPI:
    """API that grants or refuses the sweep lock."""

    def __init__(self, acquired=True):
        self.acquired = acquired
        self.calls = []

    def post(self, path, json=None):
        self.calls.append((path, json))
        if path == "/locks/acquire":
            return FakeResponse({"acquired": self.acquired, "name": json["name"]})
        return FakeResponse({"released": True})

    def get(self, path, params=None):
        return FakeResponse([])


class PolicyAPI(LockingAPI):
    def __init__(self, policy, acquired=True):
        super().__init__(acquired=acquired)
        self.policy = policy

    def get(self, path, params=None):
        if path == "/automation/policy":
            return FakeResponse({"policy": self.policy})
        return super().get(path, params)


def test_paused_policy_skips_the_whole_publishing_sweep():
    api = PolicyAPI({"paused": True, "dry_run": False, "stages": {},
                     "guardrails": {}})
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    worker._sweep = lambda now: (_ for _ in ()).throw(
        AssertionError("a paused policy must not sweep"))
    assert worker.run_once() == 0
    assert api.calls == [], "paused must not even acquire the sweep lock"


def test_lock_is_acquired_before_a_sweep_and_released_after():
    api = LockingAPI(acquired=True)
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    worker.build_adapters = lambda: {}
    worker._sweep = lambda now: 0

    worker.run_once()
    paths = [c[0] for c in api.calls]
    assert paths[0] == "/locks/acquire", "the lock must be taken BEFORE the sweep"
    assert paths[-1] == "/locks/release", "and released afterwards"


def test_a_refused_lock_skips_the_sweep():
    api = LockingAPI(acquired=False)
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    swept = []
    worker._sweep = lambda now: swept.append(1) or 0

    assert worker.run_once() == 0
    assert swept == [], "the other instance is doing the work — do not duplicate it"


def test_an_unreachable_lock_endpoint_fails_closed():
    class DeadAPI:
        def post(self, path, json=None):
            raise RuntimeError("api down")

    worker = pub.Publisher(api_url="http://fake")
    worker.api = DeadAPI()
    swept = []
    worker._sweep = lambda now: swept.append(1) or 0

    assert worker.run_once() == 0
    assert swept == [], "no proof of exclusivity — never risk a duplicate upload"


def test_a_lock_response_without_acquired_flag_is_refused():
    class IncompleteAPI(LockingAPI):
        def post(self, path, json=None):
            self.calls.append((path, json))
            if path == "/locks/acquire":
                return FakeResponse({"name": json["name"]})
            return FakeResponse({"released": True})

    worker = pub.Publisher(api_url="http://fake")
    worker.api = IncompleteAPI()
    swept = []
    worker._sweep = lambda now: swept.append(1) or 0

    assert worker.run_once() == 0
    assert swept == []
