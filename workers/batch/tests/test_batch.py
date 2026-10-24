"""Batch worker (v0.19, §10 nightly batch): the automation around the human
gates — script generation for earned offers, plus the readiness read-out that
tells the operator exactly what is waiting on whom.

Contract that must hold: the worker only decides WHEN to ask the API; the
server decides WHETHER the offer qualifies (§3 gate, unchanged)."""

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "mtk_batch_main", Path(__file__).resolve().parent.parent / "main.py")
batch_main = importlib.util.module_from_spec(_spec)
sys.modules["mtk_batch_main"] = batch_main
_spec.loader.exec_module(batch_main)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAPI:
    def __init__(self, offers=None, scripts=None, script_status=201,
                 captures=None, candidates=None, schedules=None, policy=None,
                 renders=None):
        self.offers = offers or []
        self.scripts = scripts or {}
        self.script_status = script_status
        self.captures = captures or []
        self.candidates = candidates or []
        self.schedules = schedules or []
        self.renders = renders or []
        self.policy = policy
        self.posts = []

    def get(self, path, params=None):
        if path == "/automation/policy":
            if self.policy is None:
                return FakeResponse({"policy": None}, status_code=404)
            return FakeResponse({"policy": self.policy})
        if path == "/offers":
            state = (params or {}).get("state")
            if state:
                return FakeResponse([o for o in self.offers if o["state"] == state])
            return FakeResponse(self.offers)
        if path == "/captures":
            return FakeResponse(self.captures)
        if path == "/render-candidates":
            return FakeResponse(self.candidates)
        if path == "/renders":
            return FakeResponse(self.renders)
        if path == "/schedules":
            return FakeResponse(self.schedules)
        if path.startswith("/offers/") and path.endswith("/scripts"):
            offer_id = path.split("/")[2]
            return FakeResponse(self.scripts.get(offer_id, []))
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, json=None, params=None):
        self.posts.append((path, params))
        return FakeResponse({"id": "script-1"}, status_code=self.script_status)


def _offer(offer_id="off-1", state="verified", evidence=1):
    return {"id": offer_id, "state": state, "title": "Offer", "official_evidence": evidence}


def _batch(api):
    b = batch_main.Batch(api_url="http://fake")
    b.api = api
    return b


def test_script_generated_for_earned_offer_without_script():
    api = FakeAPI(offers=[_offer()])
    b = _batch(api)
    assert b.generate_scripts() == 1
    assert api.posts[0][0] == "/offers/off-1/script"


def test_offer_without_official_evidence_is_never_scripted():
    api = FakeAPI(offers=[_offer(evidence=0)])
    b = _batch(api)
    assert b.generate_scripts() == 0
    assert api.posts == []


def test_offer_with_existing_script_is_skipped():
    api = FakeAPI(offers=[_offer()], scripts={"off-1": [{"version": 1}]})
    b = _batch(api)
    assert b.generate_scripts() == 0
    assert api.posts == []


def test_server_refusal_is_reported_not_crashed():
    api = FakeAPI(offers=[_offer()], script_status=409)
    b = _batch(api)
    assert b.generate_scripts() == 0, "the server gate refused — the worker just reports"


def test_both_script_states_are_covered():
    api = FakeAPI(offers=[_offer("off-1", "verified"), _offer("off-2", "approved_for_video")])
    b = _batch(api)
    assert b.generate_scripts() == 2


def test_readiness_counts_what_is_waiting_on_whom():
    api = FakeAPI(
        offers=[_offer("off-1", "evidence_needed"), _offer("off-2", "corrected")],
        captures=[{"id": "c1", "redaction_reviewed": False},
                  {"id": "c2", "redaction_reviewed": True}],
        candidates=[{"offer_id": "off-3"}],
        schedules=[{"id": "s1"}],
    )
    b = _batch(api)
    report = b.readiness()
    assert report["awaiting_verification"] == 1
    assert report["captures_awaiting_redaction_review"] == 1
    assert report["render_candidates"] == 1
    assert report["scheduled_posts"] == 1


def _policy(mode, paused=False):
    stages = {
        "manual": "human",
        "assisted": None,
        "autopilot": "auto",
    }
    if mode == "assisted":
        controls = {"collect": "auto", "verify": "auto", "script": "auto",
                    "render": "auto", "approve": "human", "schedule": "human"}
    else:
        controls = {stage: stages[mode] for stage in
                    ("collect", "verify", "script", "render", "approve", "schedule")}
    return {"mode": mode, "paused": paused, "dry_run": False, "stages": controls,
            "guardrails": {}}


def test_paused_policy_performs_no_state_changes():
    api = FakeAPI(offers=[_offer()], policy=_policy("autopilot", paused=True))
    b = _batch(api)
    report = b.run_once()
    assert report["paused"] is True
    assert api.posts == []


def test_manual_policy_does_not_script_or_approve():
    api = FakeAPI(offers=[_offer()], policy=_policy("manual"))
    b = _batch(api)
    report = b.run_once()
    assert report["scripts_created"] == 0
    assert report["trends_scanned"] is False  # collection stage stays human
    assert api.posts == []


def test_autopilot_claims_the_trend_scan_job_and_reports_the_result():
    class TrendAPI(FakeAPI):
        def post(self, path, json=None, params=None):
            # record the request BODY (not params) for the assertion below
            self.posts.append((path, json))
            if path == "/jobs/claim":
                return FakeResponse({"claimed": True, "id": "job-1"})
            if path == "/trends/scan":
                return FakeResponse({"created": 1, "updated": 2, "rescored": 2})
            return FakeResponse({"rearmed": True})

    api = TrendAPI(offers=[_offer()], policy=_policy("autopilot"))
    b = _batch(api)
    report = b.run_once()
    assert report["trends_scanned"] is True
    trend_posts = [p for p, _ in api.posts if p.startswith("/trends")]
    assert trend_posts == ["/trends/scan", "/trends/scan-result"]
    reported = [j for p, j in api.posts if p == "/trends/scan-result"]
    assert reported and reported[0]["ok"] is True


def test_trend_scan_failure_still_reports_so_the_job_retries():
    class FailingScanAPI(FakeAPI):
        def post(self, path, json=None, params=None):
            self.posts.append((path, json))  # record the body, not params
            if path == "/jobs/claim":
                return FakeResponse({"claimed": True, "id": "job-1"})
            if path == "/trends/scan":
                raise httpx.ConnectError("scan refused")
            return FakeResponse({"rearmed": True})

    api = FailingScanAPI(offers=[_offer()], policy=_policy("autopilot"))
    b = _batch(api)
    report = b.run_once()
    assert report["trends_scanned"] is False
    reported = [j for p, j in api.posts if p == "/trends/scan-result"]
    assert reported and reported[0]["ok"] is False and reported[0]["detail"]


def test_assisted_policy_scripts_but_leaves_approval_to_a_human():
    api = FakeAPI(offers=[_offer()], policy=_policy("assisted"))
    b = _batch(api)
    report = b.run_once()
    assert report["scripts_created"] == 1
    assert report["offers_auto_approved"] == 0
    assert report["posts_auto_scheduled"] == 0
    # The trend-scan claim + queue-expiry housekeeping may precede it
    # (assisted collects automatically); scripting is the only state-CHANGING
    # post, approval stays human.
    housekeeping = {"/jobs/claim", "/trends/scan-result", "/production-queue/expire"}
    changing = [p for p, _ in api.posts if p not in housekeeping]
    assert changing == ["/offers/off-1/script"]


def test_api_unreachable_does_not_crash_the_batch():
    class DeadAPI:
        def get(self, path, params=None):
            raise httpx.ConnectError("api down")

        def post(self, path, json=None, params=None):
            raise httpx.ConnectError("api down")

    b = _batch(DeadAPI())
    report = b.run_once()
    assert report["scripts_created"] == 0
    assert report.get("render_candidates") is None
