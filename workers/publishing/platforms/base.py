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


class RateLimited(RuntimeError):
    """The platform throttled the call (WP-G: server-shaped retry).

    Carries the server-provided delay when one is available: `retry_after_s`
    is parsed from `Retry-After` / `x-ratelimit-*` headers or the error
    payload. The publish retry path waits `max(its own backoff, retry_after_s)`
    before requeueing — hammering a throttled endpoint only extends the ban.
    """

    def __init__(self, message: str, retry_after_s: Optional[int] = None):
        super().__init__(message)
        self.retry_after_s = int(retry_after_s) if retry_after_s else None


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


def retry_after_from_response(resp: "httpx.Response") -> Optional[int]:
    """Server-shaped delay for a throttled call (WP-G).

    `Retry-After` (seconds or HTTP-date) wins; `x-ratelimit-reset` (epoch
    seconds, or seconds-until-reset as some gateways send it) is the
    fallback. Unparseable → None so the caller keeps its own backoff.
    """
    def _coerce(value) -> Optional[int]:
        try:
            seconds = int(round(float(value)))
        except (TypeError, ValueError):
            return None
        return seconds if seconds >= 0 else None

    headers = getattr(resp, "headers", None)
    if not headers:
        return None
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after:
        direct = _coerce(retry_after)
        if direct is not None:
            # seconds form; a date header parses as a huge int → sane clamp below
            if direct < 60 * 60 * 24 * 7:
                return max(0, direct)
        try:
            from email.utils import parsedate_to_datetime
            when = parsedate_to_datetime(retry_after)
            if when is not None:
                import time as _time
                return max(0, int(when.timestamp() - _time.time()))
        except (TypeError, ValueError):
            pass
    reset = headers.get("x-ratelimit-reset") or headers.get("X-RateLimit-Reset")
    if reset:
        seconds = _coerce(reset)
        if seconds is not None:
            # Some gateways send an absolute epoch (huge), some a relative
            # delay (small). Treat small values as a delay; absolute ones as
            # "at that time" only when plausibly in the future.
            if seconds < 60 * 60 * 24 * 7:
                return max(0, seconds)
            import time as _time
            delta = seconds - int(_time.time())
            if 0 <= delta < 60 * 60 * 24 * 7:
                return delta
    return None


def raise_on_graph_error(payload: dict, response: Optional["httpx.Response"] = None) -> None:
    """Meta Graph error translator (WP-G).

    190/102/105/2500 = dead session → TransportUnauthorized.
    Code 4 / subcode 2446852 (or any 'rate limit' message) = throttling →
    RateLimited with the server-provided delay when present (WP-G).
    """
    error = payload.get("error")
    if not error:
        return
    if error.get("code") in (190, 102, 105, 2500):
        raise TransportUnauthorized(error.get("message", "invalid oauth token"))
    message = str(error.get("message") or "")
    is_rate = (error.get("code") == 4
               or error.get("error_subcode") == 2446852
               or "rate limit" in message.lower())
    if is_rate:
        retry_after = retry_after_from_response(response) if response is not None else None
        raise RateLimited(
            message or "graph rate limited — retry with backoff", retry_after)
    if error:
        raise RuntimeError(f"graph error {error.get('code')}: {message}")


# ------------------------------------------------------- token lifecycle (WP-G)

def exchange_long_lived_token(base_url: str, token: str, app_id: str,
                              app_secret: str,
                              http: Optional["httpx.Client"] = None) -> dict:
    """Meta long-lived token exchange (WP-G token lifecycle, §5.6.1).

    Long-lived Page/IG tokens still expire (~60 days); the documented
    `fb_exchange_token` grant renews them WITHOUT re-auth while app id +
    secret are configured. Returns {access_token, expires_at}; raises
    TokenExpiredError on any refusal so the account can be marked expired
    and the operator sees it — never a silent stall. The token never leaves
    this process except toward Graph.
    """
    import time as _time
    from datetime import datetime, timezone

    if not (token and app_id and app_secret):
        raise TokenExpiredError(
            "long-lived token exchange needs APP_ID/APP_SECRET plus the current token")
    client = http or httpx.Client(timeout=30)
    try:
        resp = client.get(
            f"{base_url.rstrip('/')}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": token,
            },
        )
        if resp.status_code in (400, 401, 403):
            raise TokenExpiredError(
                f"token exchange refused ({resp.status_code}) — re-authentication required")
        resp.raise_for_status()
        data = resp.json() or {}
        new_token = data.get("access_token")
        if not new_token:
            raise TokenExpiredError(f"token exchange returned no token: {data.get('error')}")
        expires_dt = None
        expires_at = data.get("expires_at")
        if expires_at is None and data.get("expires_in"):
            expires_at = int(_time.time()) + int(data["expires_in"])
        if expires_at is not None:
            try:
                expires_dt = datetime.fromtimestamp(int(expires_at), timezone.utc)
            except (TypeError, ValueError, OverflowError):
                expires_dt = None
        return {"access_token": new_token, "expires_at": expires_dt}
    finally:
        if http is None:
            client.close()
