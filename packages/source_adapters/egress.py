"""Safe egress for provider fetches (master plan §6 step 2, audit A19).

A polite delay is not permission, and an allowlisted hostname is not proof that
the connection stays public: DNS can answer with an internal address and a
permitted page can redirect anywhere. This module is the single choke point for
outbound verification fetches:

- HTTPS only (plain HTTP only when a caller explicitly opts in, e.g. local
  fixtures) on a permitted port, never with embedded credentials;
- the hostname is resolved and **every** answer must be a global unicast
  address — one private answer poisons the whole name;
- every redirect hop is re-validated against the same rules;
- the body is streamed and bounded, and non-text payloads are refused.

What this does not yet do: pin the connection to the address that was
validated. A resolver that answers public during validation and private at
connect time (DNS rebinding) is a residual risk until the transport pins the
IP. Do not describe this module as a complete SSRF defence.

An HTTP error status is *returned*, not raised: a login wall, challenge or
outage means "unavailable", never proof that the offer ended or is valid.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = "MTKRadarCollector/0.2 (+https://github.com/Kaashmalik/mtk-radar)"

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
BLOCKED_HOSTNAMES = frozenset({
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
    "metadata", "metadata.google.internal",
})
BLOCKED_CONTENT_TYPES = (
    "image/", "video/", "audio/", "application/octet-stream", "application/zip",
    "application/pdf", "font/",
)


class EgressError(ValueError):
    """A destination or response violates the egress policy."""


@dataclass(frozen=True)
class EgressPolicy:
    """Bounds for one outbound fetch. Defaults are the production posture."""

    allowed_ports: frozenset[int] = frozenset({443})
    max_bytes: int = 2_000_000
    max_redirects: int = 5
    timeout: float = 20.0
    allow_plain_http: bool = False
    # Only for local fixtures (never in production): permit loopback/private
    # destinations. Kept explicit so the default cannot be relaxed by accident.
    allow_private: bool = False

    def schemes(self) -> frozenset[str]:
        return frozenset({"http", "https"}) if self.allow_plain_http else frozenset({"https"})


@dataclass(frozen=True)
class FetchResult:
    """One completed fetch, with the provenance needed to audit it later."""

    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    redirects: tuple[str, ...]
    fetched_at: datetime

    @property
    def raw_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


def is_public_address(address: str) -> bool:
    """True only for a global unicast address (never loopback/private/link-local).

    ``ipaddress`` reports multicast as ``is_global`` on some Python versions, so
    multicast is rejected explicitly.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.is_multicast:
        return False
    return bool(ip.is_global)


def validate_url(url: str, policy: EgressPolicy) -> tuple[str, int]:
    """Validate scheme, credentials, host and port. Returns (host, port).

    Host *resolution* is checked separately by :func:`safe_fetch`, because it
    must be re-checked on every redirect hop.
    """
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise EgressError(f"unparseable URL: {exc}") from None

    scheme = (parts.scheme or "").lower()
    if scheme not in policy.schemes():
        raise EgressError(
            f"scheme '{scheme or '(none)'}' refused; allowed: {sorted(policy.schemes())}"
        )
    if parts.username is not None or parts.password is not None:
        raise EgressError("URL credentials are refused; never fetch as a user")
    host = (parts.hostname or "").strip()
    if not host:
        raise EgressError("URL has no host")
    if not policy.allow_private and host.lower() in BLOCKED_HOSTNAMES:
        raise EgressError(f"host '{host}' is blocked")
    try:
        port = parts.port
    except ValueError:
        raise EgressError("URL has an invalid port") from None
    if port is None:
        port = 443 if scheme == "https" else 80
    if port not in policy.allowed_ports:
        raise EgressError(
            f"port {port} refused; allowed: {sorted(policy.allowed_ports)}"
        )
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not policy.allow_private and not is_public_address(host):
        raise EgressError(f"IP literal '{host}' is not a public address")
    return host, port


def _default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def _resolve_public(host: str, port: int, resolver: Callable[[str, int], list[str]],
                   *, allow_private: bool = False) -> None:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not allow_private and not is_public_address(host):
            raise EgressError(f"IP literal '{host}' is not a public address")
        return
    try:
        addresses = resolver(host, port)
    except EgressError:
        raise
    except Exception as exc:  # noqa: BLE001 — DNS failure is a policy failure
        raise EgressError(f"could not resolve host '{host}': {exc}") from None
    if not addresses:
        raise EgressError(f"could not resolve host '{host}': no addresses")
    if allow_private:
        return
    non_public = [address for address in addresses if not is_public_address(address)]
    if non_public:
        raise EgressError(
            f"host '{host}' resolves to a non-public address ({', '.join(non_public)}); refused"
        )


def _check_content_type(content_type: str) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    if base.startswith(BLOCKED_CONTENT_TYPES):
        raise EgressError(f"content type '{base}' is not reviewed text; refused")
    return base


def safe_fetch(
    url: str,
    *,
    policy: Optional[EgressPolicy] = None,
    client: Optional[httpx.Client] = None,
    resolver: Optional[Callable[[str, int], list[str]]] = None,
    clock: Optional[Callable[[], datetime]] = None,
    before_request: Optional[Callable[[str], None]] = None,
) -> FetchResult:
    """Fetch one provider page through the egress policy.

    Redirects are followed manually so every hop is validated. A non-2xx final
    status is returned to the caller rather than raised. `before_request` runs
    per hop so a caller can apply per-host politeness delays.
    """
    policy = policy or EgressPolicy()
    resolver = resolver or _default_resolver
    clock = clock or (lambda: datetime.now(timezone.utc))
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=policy.timeout,
            follow_redirects=False,
        )

    requested = str(url)
    current = requested
    redirects: list[str] = []
    try:
        for _ in range(policy.max_redirects + 1):
            host, port = validate_url(current, policy)
            _resolve_public(host, port, resolver, allow_private=policy.allow_private)
            if before_request is not None:
                before_request(current)

            with client.stream("GET", current) as response:
                status = response.status_code
                if status in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise EgressError(f"redirect {status} without a location header")
                    current = urljoin(str(response.url), location)
                    redirects.append(current)
                    continue

                content_type = _check_content_type(
                    response.headers.get("content-type", "")
                )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > policy.max_bytes:
                        raise EgressError(
                            f"response too large (limit {policy.max_bytes} bytes)"
                        )
                    chunks.append(chunk)
                fetched_at = clock()
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                return FetchResult(
                    requested_url=requested,
                    final_url=str(response.url),
                    status=status,
                    content_type=content_type,
                    body=b"".join(chunks),
                    redirects=tuple(redirects),
                    fetched_at=fetched_at,
                )
        raise EgressError(
            f"too many redirects (limit {policy.max_redirects})"
        )
    finally:
        if own_client:
            client.close()
