"""Per-account circuit breaker for the publishing worker (EP-07).

A platform account that keeps failing (outage, revoked app permission,
throttling) used to be hit on every sweep for every queued post, burning
quota and producing a wall of held failures. After `threshold` consecutive
failures for one (platform, account) the breaker OPENS: that account's posts
are skipped — left scheduled, never marked failed — for `cooldown_s`. Then
it is HALF-OPEN: one post may try; success closes it, failure re-opens it.

State is per process and in memory on purpose: a restart is a fresh probe,
and no breaker state can ever block a post permanently.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

DEFAULT_THRESHOLD = 3
DEFAULT_COOLDOWN_S = 900.0


@dataclass
class _State:
    failures: int = 0
    opened_at: Optional[float] = None
    probing: bool = False


class AccountBreaker:
    def __init__(self, threshold: int = DEFAULT_THRESHOLD,
                 cooldown_s: float = DEFAULT_COOLDOWN_S,
                 clock: Callable[[], float] = time.monotonic):
        self.threshold = max(1, int(threshold))
        self.cooldown_s = max(0.0, float(cooldown_s))
        self._clock = clock
        self._states: dict[tuple[str, str], _State] = {}

    @classmethod
    def from_env(cls) -> "AccountBreaker":
        def _num(name: str, default: float) -> float:
            try:
                return float(os.environ.get(name, default))
            except ValueError:
                return default
        return cls(threshold=int(_num("MTK_PUBLISH_BREAKER_THRESHOLD", DEFAULT_THRESHOLD)),
                   cooldown_s=_num("MTK_PUBLISH_BREAKER_COOLDOWN_S", DEFAULT_COOLDOWN_S))

    @staticmethod
    def key(platform: str, account_id: Optional[str]) -> tuple[str, str]:
        return (str(platform), str(account_id or "default"))

    def allow(self, key: tuple[str, str]) -> tuple[bool, float]:
        """(allowed, seconds until the next probe when refused)."""
        state = self._states.get(key)
        if state is None or state.opened_at is None:
            return True, 0.0
        remaining = state.opened_at + self.cooldown_s - self._clock()
        if remaining > 0:
            return False, remaining
        if state.probing:
            return False, 0.0  # one probe at a time in half-open
        state.probing = True
        return True, 0.0

    def success(self, key: tuple[str, str]) -> None:
        self._states.pop(key, None)

    def failure(self, key: tuple[str, str], *, min_open_s: float = 0.0) -> bool:
        """Record a failure; True when this failure opened (or re-opened) it.

        `min_open_s` lets a server-shaped delay (Retry-After) hold the
        breaker open at least that long.
        """
        state = self._states.setdefault(key, _State())
        state.failures += 1
        reopen = state.probing or state.failures >= self.threshold
        state.probing = False
        if reopen:
            # Shift the open time so the effective wait is max(cooldown, min_open_s).
            extra = max(0.0, min_open_s - self.cooldown_s)
            state.opened_at = self._clock() + extra
        return reopen

    def is_open(self, key: tuple[str, str]) -> bool:
        state = self._states.get(key)
        return bool(state and state.opened_at is not None)
