"""Durable jobs-queue drain (v0.33): the publishing worker claims
publish_schedule jobs (SKIP LOCKED + lease + reported result) instead of
relying only on list polling. The sweep is still the fallback; these tests
pin the job-driven contract:

- a claimed, due, scheduled post drives a REAL upload and is reported done;
- a claimed post in any other state resolves the job without uploading
  (nothing owed — the human/queue already decided);
- a claimed post that is not yet due re-queues with a retry_after, burning
  no upload;
- a schedule vanished mid-lease: the job resolves as nothing-owed;
- an older API without /jobs/claim (404) degrades to sweep-only, silently;
- the MTK_PUBLISH_JOB_QUEUE=0 knob disables the drain entirely.
"""

import importlib.util
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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
        self.text = ""

    def json(self):
        return self._payload


class FakeAdapter:
    def __init__(self):
        self.uploads = []
        self.confirmations = []

    def confirm_publication(self, remote_id, *, expected_privacy,
                            timeout_s=300, interval_s=5.0):
        # G02: reconciliation is part of a real upload, so the fake does it too.
        self.confirmations.append((remote_id, expected_privacy))
        return {"confirmed": True, "processing_state": "ready",
                "remote_url": "https://example.test/v/remote-1"}

    def upload(self, path, meta, privacy=None, idempotency_key=None):
        self.uploads.append((path, meta, privacy, idempotency_key))
        return "remote-1"


def _real_video() -> str:
    path = Path(tempfile.mkdtemp()) / "job-queue.mp4"
    path.write_bytes(b"VIDEO-JOB-QUEUE")
    return str(path)


def _render(video_path):
    return {"id": "r1", "offer_id": "off-1", "video_path": video_path,
            "script_version_hash": "APPROVED",
            "cover_path": None, "captions_path": None,
            "status": "rendered", "qc_status": "passed"}


def _schedule(video_path, state="scheduled", due=True):
    """A post whose pins match the render exactly (same construction as the
    gate tests) so the only variable under test is the job lifecycle."""
    metadata = {
        "title": "Approved title",
        "caption": "Approved caption with the reviewed CTA.",
        "captions_language": "en",
    }
    local_time = ("2020-01-01T00:00:00+00:00" if due
                  else (datetime.now(timezone.utc) + timedelta(hours=6))
                  .isoformat())
    post = {
        "id": "sch-1", "state": state, "platform": "youtube",
        "offer_id": "off-1", "local_time": local_time, "privacy": "private",
        "version_hash": "APPROVED", "metadata": metadata,
        "idempotency_key": "k-1", "outcome_detail": None, "language": "en",
        "caption_variant": "default", "metadata_variant": "default",
        "render_id": "r1", "render_sha256": pub._sha256_file(Path(video_path)),
        "metadata_hash": pub._canonical_hash(metadata),
        "cover_sha256": None, "captions_sha256": None, "pinned_comment": None,
        "youtube_playlist_id": None, "platform_account_id": None,
        "cover_path": None,
    }
    post["package_hash"] = pub._canonical_hash({
        "offer_id": "off-1", "platform": "youtube", "account_id": None,
        "render_id": "r1", "render_sha256": post["render_sha256"],
        "metadata_hash": post["metadata_hash"],
        "cover_sha256": None, "captions_sha256": None,
        "script_version_hash": "APPROVED", "language": "en",
        "privacy": "private", "caption_variant": "default",
        "metadata_variant": "default", "pinned_comment": None,
        "youtube_playlist_id": None,
    })
    return post


class JobQueueAPI:
    """FakeAPI whose /jobs endpoints speak the real queue contract."""

    def __init__(self, schedule=None, claim_status=200, claim_body=None,
                 video_path=None):
        self.video_path = video_path or _real_video()
        self.schedule = schedule if schedule is not None \
            else _schedule(self.video_path)
        self.claim_status = claim_status
        self.claim_body = claim_body if claim_body is not None else {
            "claimed": True, "id": "job-1", "kind": "publish_schedule",
            "entity_id": "sch-1", "payload": {}, "attempt": 1,
        }
        self.results = []
        self.claims = 0

    def get(self, path, params=None):
        if path == "/schedules/sch-1":
            return FakeResponse(self.schedule)
        if path == "/renders":
            return FakeResponse([_render(self.video_path)])
        if path.startswith("/renders/"):
            return FakeResponse(_render(self.video_path))
        if path.startswith("/offers/"):
            return FakeResponse({"id": "off-1", "state": "verified",
                                 "expires_at": (datetime.now(timezone.utc)
                                                + timedelta(days=1)).isoformat(),
                                 "recheck_at": (datetime.now(timezone.utc)
                                                + timedelta(days=1)).isoformat()})
        if path == "/platform-accounts":
            return FakeResponse([])  # a list; the upload test patches build_adapters
        if path == "/schedules":
            return FakeResponse([])
        if path.endswith("/release-check"):
            return FakeResponse({"ok": True, "problems": []})
        return FakeResponse({})

    def post(self, path, json=None):  # noqa: A002
        if path == "/jobs/claim":
            self.claims += 1
            if self.results:  # job already resolved — the queue is dry
                return FakeResponse({"claimed": False})
            return FakeResponse(self.claim_body, self.claim_status)
        if path.startswith("/jobs/") and path.endswith("/result"):
            self.results.append((path.split("/")[2], json))
            return FakeResponse({"id": path.split("/")[2], "status": "done"})
        if path.endswith("/attempt"):
            return FakeResponse({"acquired": True, "attempt_token": "token-1"})
        if path.endswith("/result"):
            return FakeResponse({"ok": bool(json and json.get("ok"))})
        return FakeResponse({"ok": True})


def _publisher(api):
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    worker.policy = {}
    return worker


def test_claimed_due_job_drives_a_real_upload(monkeypatch):
    api = JobQueueAPI()
    worker = _publisher(api)
    adapter = FakeAdapter()
    monkeypatch.setattr(worker, "build_adapters", lambda: {"youtube": adapter})
    published = worker._drain_publish_jobs(datetime.now(timezone.utc))
    assert published == 1
    # claim #1 takes the job; claim #2 empties the queue (claimed=False)
    assert api.claims == 2
    assert len(adapter.uploads) == 1, "the claimed job must drive the upload"
    job_id, payload = api.results[0]
    assert (job_id, payload["ok"]) == ("job-1", True)


def test_non_scheduled_state_resolves_job_without_uploading():
    video = _real_video()
    api = JobQueueAPI(schedule=_schedule(video, state="cancelled"), video_path=video)
    worker = _publisher(api)
    published = worker._drain_publish_jobs(datetime.now(timezone.utc))
    assert published == 0
    assert len(api.results) == 1
    assert api.results[0][1]["ok"] is True
    assert "cancelled" in api.results[0][1]["detail"]


def test_not_yet_due_job_requeues_with_retry_after():
    video = _real_video()
    api = JobQueueAPI(schedule=_schedule(video, due=False), video_path=video)
    worker = _publisher(api)
    published = worker._drain_publish_jobs(datetime.now(timezone.utc))
    assert published == 0
    _, payload = api.results[0]
    assert payload["ok"] is False
    assert 0 < payload["retry_after_s"] <= 6 * 3600


def test_missing_schedule_resolves_nothing_owed():
    api = JobQueueAPI(claim_body={"claimed": True, "id": "job-1",
                                  "kind": "publish_schedule",
                                  "entity_id": "sch-1", "payload": {},
                                  "attempt": 1})

    class _Missing(JobQueueAPI):
        def get(self, path, params=None):
            if path == "/schedules/sch-1":
                return FakeResponse({"detail": "schedule not found"}, 404)
            return JobQueueAPI.get(self, path, params)

    api2 = _Missing()
    worker = _publisher(api2)
    published = worker._drain_publish_jobs(datetime.now(timezone.utc))
    assert published == 0
    assert api2.results[0][1]["ok"] is True  # nothing owed


def test_older_api_without_jobs_claim_degrades_to_sweep_only():
    api = JobQueueAPI(claim_status=404, claim_body={"detail": "not found"})
    worker = _publisher(api)
    assert worker._drain_publish_jobs(datetime.now(timezone.utc)) == 0
    assert api.claims == 1
    assert api.results == []


def test_queue_unreachable_degrades_to_sweep_only():
    class _DeadAPI:
        def post(self, path, json=None):  # noqa: A002
            raise pub.httpx.ConnectError("down")

    worker = _publisher(_DeadAPI())
    assert worker._drain_publish_jobs(datetime.now(timezone.utc)) == 0


def test_knob_disables_the_drain(monkeypatch):
    monkeypatch.setenv("MTK_PUBLISH_JOB_QUEUE", "0")
    api = JobQueueAPI()
    worker = _publisher(api)
    assert worker._drain_publish_jobs(datetime.now(timezone.utc)) == 0
    assert api.claims == 0
