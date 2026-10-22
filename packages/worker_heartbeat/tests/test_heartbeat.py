import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from worker_heartbeat import WorkerHeartbeat, heartbeat_once  # noqa: E402


def test_payload_is_operational_only_and_names_worker():
    hb = WorkerHeartbeat("http://api:8000/", "render", interval_s=60,
                         metadata={"toolchain": {"ffmpeg": "/usr/bin/ffmpeg"}})
    payload = hb.payload("ok", "rendering")
    assert payload["worker"] == "render"
    assert payload["status"] == "ok"
    assert payload["interval_s"] == 60
    assert payload["metadata"]["toolchain"]["ffmpeg"] == "/usr/bin/ffmpeg"
    assert "token" not in str(payload).lower()


def test_disabled_heartbeat_never_calls_network():
    hb = WorkerHeartbeat("", "monitor")
    assert hb.enabled is False
    assert hb.beat() is False
    hb.start()
    hb.stop()


def test_heartbeat_is_best_effort_when_api_is_down():
    hb = WorkerHeartbeat("http://127.0.0.1:1", "batch", interval_s=5)
    assert hb.enabled is True
    assert hb.beat() is False  # swallowed, never raises


def test_once_helper_does_not_raise_when_unreachable():
    assert heartbeat_once("http://127.0.0.1:1", "metrics") is False
