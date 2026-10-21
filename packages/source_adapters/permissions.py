"""Provider permission checks for outbound reads (master plan §3, §6 step 2).

A politeness delay is not permission. Before reading an official page the
acquisition worker asks the host what its ``robots.txt`` allows, records that
answer with the evidence it derives, and refuses to act when the policy cannot
be read. The decision is *fail-closed*:

- ``2xx`` — the file is parsed; ``can_fetch`` decides (RFC 9309 matching);
- ``404``/``410``/other ``4xx`` (except the auth/ratelimit ones) — no policy
  published, so the page may be read;
- ``401``/``403``/``429`` and every ``5xx`` — the policy is unreadable or says
  "not for you"; treat as a refusal, never as consent;
- a transport or egress-policy failure — refusal.

The check itself goes through :func:`source_adapters.egress.safe_fetch`, so
``robots.txt`` is fetched under exactly the same SSRF/egress rules as the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .client import Fetcher
from .egress import USER_AGENT, EgressError, EgressPolicy

ROBOTS_PATH = "/robots.txt"
#: Statuses that mean "there is no published policy" rather than "you may not".
_ABSENT_ROBOTS_STATUSES = frozenset({400, 404, 410, 451})


@dataclass(frozen=True)
class RobotsDecision:
    """What the host said about this fetch, and when we asked."""

    domain: str
    robots_url: str
    checked_at: datetime
    allowed: bool
    status: Optional[int]
    reason: str

    def as_provenance(self) -> dict:
        """Shape recorded with the evidence (never invented after the fact)."""
        return {
            "robots_url": self.robots_url,
            "checked_at": self.checked_at.isoformat(),
            "allowed": self.allowed,
            "status": self.status,
        }


def _decision(domain: str, robots_url: str, checked_at: datetime, *,
              allowed: bool, status: Optional[int], reason: str) -> RobotsDecision:
    return RobotsDecision(
        domain=domain, robots_url=robots_url, checked_at=checked_at,
        allowed=allowed, status=status, reason=reason,
    )


def check_robots(
    domain: str,
    *,
    fetcher: Optional[Fetcher] = None,
    user_agent: str = USER_AGENT,
    policy: Optional[EgressPolicy] = None,
    clock: Optional[Callable[[], datetime]] = None,
    path: str = "/",
) -> RobotsDecision:
    """Decide whether ``user_agent`` may read ``https://<domain><path>``.

    Returns the decision whether or not it permits the fetch; callers that must
    not proceed raise :class:`PermissionDenied` (or skip the page). The decision
    is never cached here — the caller decides how long an answer stays valid.
    """
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    raw_domain = (domain or "").strip().lower()
    robots_url = f"https://{raw_domain}{ROBOTS_PATH}"
    if not raw_domain or "/" in raw_domain or "@" in raw_domain or " " in raw_domain:
        return _decision(
            raw_domain, robots_url, now, allowed=False, status=None,
            reason="invalid provider host; refusing to guess a robots policy",
        )
    try:
        host = urlsplit(robots_url).hostname
    except ValueError:
        host = None
    if host != raw_domain:
        return _decision(
            raw_domain, robots_url, now, allowed=False, status=None,
            reason="provider host is not a bare DNS name; refusing to guess",
        )

    fetcher = fetcher or Fetcher()
    try:
        result = fetcher.safe_fetch(
            robots_url, policy=policy or EgressPolicy(), clock=clock,
        )
    except EgressError as exc:
        # The robots file itself is not reachable within the egress policy.
        # That is not permission.
        return _decision(
            raw_domain, robots_url, now, allowed=False, status=None,
            reason=f"robots.txt could not be fetched safely: {exc}",
        )
    except httpx.HTTPError as exc:
        return _decision(
            raw_domain, robots_url, now, allowed=False, status=None,
            reason=f"robots.txt unreachable: {exc.__class__.__name__}",
        )

    status = result.status
    if status in _ABSENT_ROBOTS_STATUSES:
        return _decision(
            raw_domain, robots_url, now, allowed=True, status=status,
            reason=f"robots.txt returned HTTP {status}; no published policy",
        )
    if not 200 <= status < 300:
        # 401/403 (auth wall), 429 (rate limit) and every 5xx mean the policy
        # is unknown or explicitly withheld. Never read that as consent.
        return _decision(
            raw_domain, robots_url, now, allowed=False, status=status,
            reason=f"robots.txt returned HTTP {status}; refusing until it can be read",
        )

    parser = RobotFileParser()
    try:
        parser.parse(result.body.decode("utf-8", "replace").splitlines())
        allowed = bool(parser.can_fetch(user_agent, f"https://{raw_domain}{path}"))
    except Exception:  # noqa: BLE001 — an unparseable policy is not permission
        return _decision(
            raw_domain, robots_url, now, allowed=False, status=status,
            reason="robots.txt could not be parsed; treating as a refusal",
        )
    return _decision(
        raw_domain, robots_url, now, allowed=allowed, status=status,
        reason=(
            "robots.txt permits this fetch" if allowed
            else "robots.txt disallows this fetch"
        ),
    )
