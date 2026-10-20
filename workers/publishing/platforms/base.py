"""Publishing adapter base + shared errors (master plan §6).

Official APIs only — no browser automation to evade platform rules (§6).
Adapters receive an injectable httpx.Client so every call is testable with a
mocked transport; nothing here touches the network in unit tests.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Optional

import httpx


class TokenExpiredError(RuntimeError):
    """Refresh failed or the platform reports a dead session — the worker must
    pause the queue and alert the operator (token-expiry recovery, §6)."""


class NotConfiguredError(RuntimeError):
    """Platform credentials missing — skip the post without a failure state."""


class TransportUnauthorized(Exception):
    """HTTP 401/invalid-token inside one attempt; adapters translate + retry."""


class PublishAdapter(ABC):
    platform: str = "abstract"

    def __init__(self, account_id: Optional[str] = None,
                 on_refresh: Optional[Callable[[Any], None]] = None):
        # account_id links token refreshes back to the platform_accounts row;
        # on_refresh receives the new expiry (never the token itself).
        self.account_id = account_id
        self.on_refresh = on_refresh

    @abstractmethod
    def upload(self, video_path: Path, meta: dict[str, Any],
               privacy: str = "private", idempotency_key: str | None = None) -> str:
        """Upload and return the remote post/video id."""

    @abstractmethod
    def ensure_ready(self) -> None:
        """Refresh tokens if near expiry; raise TokenExpiredError if beyond recovery."""


def raise_on_graph_error(payload: dict) -> None:
    """Meta Graph error code 190 (and friends) = dead session."""
    error = payload.get("error")
    if error and error.get("code") in (190, 102, 105, 2500):
        raise TransportUnauthorized(error.get("message", "invalid oauth token"))
    if error and error.get("code") == 4:
        raise RuntimeError("graph rate limited — retry with backoff")
    if error:
        raise RuntimeError(f"graph error {error.get('code')}: {error.get('message')}")
