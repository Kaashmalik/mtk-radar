"""Best-effort worker heartbeats for MTK RADAR (v0.30).

A worker should never fail its real job because the API is briefly
unavailable. Every call here therefore catches transport errors, logs once,
and continues. The API treats a missing/stale heartbeat as an alert, so a
worker that cannot report is visible instead of silently dead.

Typical use::

    hb = WorkerHeartbeat(args.api, "publishing", interval_s=60)
    hb.start()
    try:
        worker.run_forever()
    finally:
        hb.stop()
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from typing import Any, Optional

import httpx

log = logging.getLogger("worker.heartbeat")

DEFAULT_INTERVAL_S = 60


class WorkerHeartbeat:
    """Periodic heartbeat reporter with a daemon thread.

    ``interval_s`` is the beat cadence, not the worker's sweep interval. Keep
    it short (the default is 60s) so a long render or a sleeping loop does not
    look dead.
    """

    def __init__(
        self,
        api_url: str,
        worker: str,
        *,
        interval_s: int = DEFAULT_INTERVAL_S,
        metadata: Optional[dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self.api_url = (api_url or "").strip().rstrip("/")
        self.worker = worker.strip().lower()
        self.interval_s = max(5, min(int(interval_s or DEFAULT_INTERVAL_S), 86400))
        self.metadata = dict(metadata or {})
        self.auth_token = (
            auth_token if auth_token is not None
            else os.environ.get("MTK_API_TOKEN", "")
        ).strip()
        if enabled is None:
            enabled = os.environ.get("MTK_WORKER_HEARTBEATS", "1").strip() not in (
                "0", "false", "False", "no", "off",
            )
        self.enabled = bool(enabled and self.api_url)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._warned = False

    # ------------------------------------------------------------- payload

    def payload(self, status: str = "ok", detail: Optional[str] = None) -> dict[str, Any]:
        return {
            "worker": self.worker,
            "status": status,
            "detail": detail,
            "metadata": self.metadata,
            "interval_s": self.interval_s,
        }

    def _headers(self) -> dict[str, str]:
        if not self.auth_token:
            return {}
        return {"Authorization": f"Bearer {self.auth_token}"}

    # ---------------------------------------------------------------- beat

    def beat(self, status: str = "ok", detail: Optional[str] = None) -> bool:
        """POST one best-effort beat. Returns True on success."""
        if not self.enabled:
            return False
        try:
            response = httpx.post(
                f"{self.api_url}/workers/heartbeat",
                json=self.payload(status, detail),
                headers=self._headers(),
                timeout=5.0,
            )
            response.raise_for_status()
            if self._warned:
                log.info("heartbeat to %s recovered for %s", self.api_url, self.worker)
                self._warned = False
            return True
        except Exception as exc:  # noqa: BLE001 — heartbeat must never break the worker
            if not self._warned:
                log.warning(
                    "heartbeat failed for %s at %s: %s (will keep trying)",
                    self.worker, self.api_url, exc,
                )
                self._warned = True
            return False

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            self.beat("ok")

    def start(self) -> "WorkerHeartbeat":
        if not self.enabled or self._thread is not None:
            return self
        self.beat("starting", detail="worker starting")
        self._thread = threading.Thread(
            target=self._loop,
            name=f"heartbeat-{self.worker}",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=6.0)
        self._thread = None
        self.beat("stopped", detail="worker stopped")

    def __enter__(self) -> "WorkerHeartbeat":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.stop()


def heartbeat_once(
    api_url: str,
    worker: str,
    *,
    detail: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    auth_token: Optional[str] = None,
) -> bool:
    """Send one beat for a one-shot/cron invocation (no background thread)."""
    hb = WorkerHeartbeat(
        api_url, worker, interval_s=DEFAULT_INTERVAL_S,
        metadata=metadata, auth_token=auth_token,
    )
    return hb.beat("ok", detail=detail or "one-shot run")


__all__ = ["DEFAULT_INTERVAL_S", "WorkerHeartbeat", "heartbeat_once"]


def lease_holder(role: str) -> str:
    """Unique job-lease holder for THIS process: ``<role>-<host>-<pid>``.

    Lease fencing only works when holders are distinct. A shared name such as
    "render-worker" let two processes renew and settle each other's jobs, so
    a worker whose lease expired could still overwrite the new holder's
    outcome. Bounded to the API's 120-character holder limit.
    """
    host = (socket.gethostname() or "host").split(".")[0]
    return f"{role}-{host}-{os.getpid()}"[:120]

