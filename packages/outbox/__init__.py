"""Durable file outbox for best-effort deliveries (EP-07, 2026-10-28 plan).

Cost telemetry and monitor notifications used to be fire-and-forget: if the
API or the webhook/mail server was down at that moment, the record was gone —
spend went unmetered and a transient alert was never seen. Callers now put a
record here when delivery fails and replay it later.

Design (no extra service, no database dependency):
- one JSON file per record, written to a temp name and atomically renamed, so
  a crash mid-write leaves an ignorable ``.tmp`` and never a half record;
- the record id is the CALLER's idempotency key: putting the same id twice
  is a no-op, and receivers deduplicate replays by that id;
- exponential backoff per record (``next_at``), a dead-letter folder after
  ``max_attempts`` or on a permanent refusal, and a hard cap on pending
  records so an outage cannot fill the disk (the oldest are dead-lettered,
  never silently deleted).

Thread- and multi-process-safe enough for this use: every mutation is an
atomic rename of a whole file; concurrent flushers may both send a record,
which the id-based deduplication on the receiving side absorbs.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

log = logging.getLogger("outbox")

def default_dir() -> str:
    """MTK_OUTBOX_DIR, read at construction time (tests and containers set it)."""
    return os.environ.get("MTK_OUTBOX_DIR") or os.path.join(
        os.path.expanduser("~"), ".mtk-radar", "outbox")
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


@dataclass
class Pending:
    id: str
    payload: Any
    attempts: int
    created_at: float
    next_at: float


class FileOutbox:
    def __init__(self, name: str, root: str | os.PathLike | None = None, *,
                 max_pending: int = 5000, max_attempts: int = 20,
                 base_backoff_s: float = 30.0, max_backoff_s: float = 3600.0,
                 clock: Callable[[], float] = time.time):
        self.dir = Path(root or default_dir()) / _SAFE_ID.sub("_", name)
        self.dead_dir = self.dir / "dead"
        self.max_pending = max(1, int(max_pending))
        self.max_attempts = max(1, int(max_attempts))
        self.base_backoff_s = float(base_backoff_s)
        self.max_backoff_s = float(max_backoff_s)
        self._clock = clock

    # ------------------------------------------------------------- storage

    def _path(self, record_id: str) -> Path:
        safe = _SAFE_ID.sub("_", str(record_id))[:180]
        if not safe:
            raise ValueError("outbox record id is empty")
        return self.dir / f"{safe}.json"

    def _write(self, path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(record, default=str), encoding="utf-8")
        os.replace(tmp, path)

    def _read(self, path: Path) -> Optional[dict]:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return record if isinstance(record, dict) and "id" in record else None

    # ---------------------------------------------------------------- API

    def put(self, record_id: str, payload: Any) -> bool:
        """Spool a record; False when it was already pending (idempotent)."""
        path = self._path(record_id)
        if path.exists():
            return False
        now = self._clock()
        self._write(path, {"id": str(record_id), "payload": payload, "attempts": 0,
                           "created_at": now, "next_at": now})
        self._enforce_cap()
        return True

    def pending_count(self) -> int:
        return sum(1 for _ in self._files())

    def due(self, limit: int = 50) -> list[Pending]:
        """Records whose backoff has elapsed, oldest first."""
        now = self._clock()
        out: list[Pending] = []
        for path in sorted(self._files(), key=lambda p: p.stat().st_mtime):
            record = self._read(path)
            if record is None:
                continue
            if float(record.get("next_at", 0)) <= now:
                out.append(Pending(record["id"], record.get("payload"),
                                   int(record.get("attempts", 0)),
                                   float(record.get("created_at", now)),
                                   float(record.get("next_at", now))))
                if len(out) >= limit:
                    break
        return out

    def ack(self, record_id: str) -> None:
        try:
            self._path(record_id).unlink()
        except FileNotFoundError:
            pass

    def fail(self, record_id: str, *, permanent: bool = False,
             error: str | None = None) -> None:
        """Back off (or dead-letter) a record whose delivery failed again."""
        path = self._path(record_id)
        record = self._read(path)
        if record is None:
            return
        record["attempts"] = int(record.get("attempts", 0)) + 1
        if error:
            record["last_error"] = str(error)[:500]
        if permanent or record["attempts"] >= self.max_attempts:
            self._dead_letter(path, record)
            return
        backoff = min(self.max_backoff_s,
                      self.base_backoff_s * (2 ** (record["attempts"] - 1)))
        record["next_at"] = self._clock() + backoff
        self._write(path, record)

    def flush(self, send: Callable[[Any], Optional[bool]], limit: int = 50) -> dict:
        """Replay due records through `send(payload)`.

        `send` returns True (delivered → ack), False (retryable → back off) or
        None (permanently refused → dead letter). Exceptions count as
        retryable failures, so a crashing transport cannot lose records.
        """
        stats = {"sent": 0, "retry": 0, "dead": 0}
        for pending in self.due(limit):
            try:
                outcome = send(pending.payload)
            except Exception as exc:  # noqa: BLE001 — never lose a record
                outcome, error = False, f"{type(exc).__name__}: {exc}"
            else:
                error = None
            if outcome is True:
                self.ack(pending.id)
                stats["sent"] += 1
            elif outcome is None:
                self.fail(pending.id, permanent=True, error=error or "refused")
                stats["dead"] += 1
            else:
                self.fail(pending.id, error=error or "delivery failed")
                stats["retry"] += 1
        return stats

    # ------------------------------------------------------------ internal

    def _files(self) -> Iterator[Path]:
        if not self.dir.is_dir():
            return iter(())
        return (p for p in self.dir.glob("*.json") if p.is_file())

    def _dead_letter(self, path: Path, record: dict) -> None:
        self._write(self.dead_dir / path.name, record)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        log.error("outbox %s: record %s dead-lettered after %s attempt(s)",
                  self.dir.name, record.get("id"), record.get("attempts"))

    def _enforce_cap(self) -> None:
        files = list(self._files())
        overflow = len(files) - self.max_pending
        if overflow <= 0:
            return
        for path in sorted(files, key=lambda p: p.stat().st_mtime)[:overflow]:
            record = self._read(path) or {"id": path.stem}
            record["last_error"] = "outbox full — oldest record moved to dead letter"
            self._dead_letter(path, record)
