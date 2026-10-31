"""Durable outbox — failure-injection contracts (EP-07)."""

import os

from outbox import FileOutbox


class Clock:
    def __init__(self):
        self.t = 1_000.0

    def __call__(self):
        return self.t


def _box(tmp_path, **kw):
    clock = Clock()
    return FileOutbox("usage", tmp_path, clock=clock, **kw), clock


def test_put_is_idempotent_by_record_id(tmp_path):
    box, _ = _box(tmp_path)
    assert box.put("evt-1", {"units": 5}) is True
    assert box.put("evt-1", {"units": 999}) is False, "duplicate delivery ignored"
    assert box.due()[0].payload == {"units": 5}


def test_api_outage_then_recovery_delivers_every_record_once(tmp_path):
    box, clock = _box(tmp_path, base_backoff_s=10)
    for i in range(3):
        box.put(f"e{i}", i)
    down = box.flush(lambda payload: False)
    assert down == {"sent": 0, "retry": 3, "dead": 0}
    assert box.due() == [], "backing off — nothing due yet"
    clock.t += 11
    delivered = []
    up = box.flush(lambda payload: delivered.append(payload) or True)
    assert up["sent"] == 3 and sorted(delivered) == [0, 1, 2]
    assert box.pending_count() == 0


def test_transport_exception_and_timeouts_never_lose_a_record(tmp_path):
    box, clock = _box(tmp_path)
    box.put("e", "x")

    def boom(payload):
        raise TimeoutError("provider timed out")

    assert box.flush(boom)["retry"] == 1
    assert box.pending_count() == 1


def test_backoff_grows_and_permanent_refusal_dead_letters(tmp_path):
    box, clock = _box(tmp_path, base_backoff_s=10, max_backoff_s=25)
    box.put("e", "x")
    box.fail("e")
    first = box.due(limit=10)
    assert first == []
    clock.t += 10
    box.fail("e")                     # second failure → 20 s
    clock.t += 19
    assert box.due() == []
    clock.t += 1
    assert len(box.due()) == 1
    box.flush(lambda payload: None)   # 4xx-style refusal
    assert box.pending_count() == 0
    assert (box.dead_dir / "e.json").exists()


def test_max_attempts_dead_letters(tmp_path):
    box, clock = _box(tmp_path, max_attempts=2, base_backoff_s=0)
    box.put("e", "x")
    box.flush(lambda payload: False)
    box.flush(lambda payload: False)
    assert box.pending_count() == 0 and (box.dead_dir / "e.json").exists()


def test_cap_moves_oldest_to_dead_letter_not_the_void(tmp_path):
    box, clock = _box(tmp_path, max_pending=2)
    for i in range(3):
        box.put(f"e{i}", i)
        path = box._path(f"e{i}")
        os.utime(path, (1000 + i, 1000 + i))
    assert box.pending_count() == 2
    assert len(list(box.dead_dir.glob("*.json"))) == 1


def test_crash_mid_write_leaves_only_an_ignored_tmp(tmp_path):
    box, _ = _box(tmp_path)
    box.put("ok", 1)
    (box.dir / "half.json.123.tmp").write_text("{not json")
    (box.dir / "corrupt.json").write_text("{not json")
    assert [p.id for p in box.due()] == ["ok"]


def test_unsafe_ids_are_sanitised_into_the_folder(tmp_path):
    box, _ = _box(tmp_path)
    box.put("../../etc/passwd", 1)
    assert all(p.parent == box.dir for p in box.dir.glob("*.json"))
