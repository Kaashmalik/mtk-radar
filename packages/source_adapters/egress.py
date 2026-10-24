"""Safe egress for provider fetches (master plan §6 step 2, audit A19).

A polite delay is not permission, and an allowlisted hostname is not proof that
the connection stays public: DNS can answer with an internal address and a
permitted page can redirect anywhere. This module is the single choke point for
outbound verification fetches:

- HTTPS only (plain HTTP only when a caller explicitly opts in, e.g. local
  fixtures) on a permitted port, never with embedded credentials;
- the hostname is resolved and **every** answer must be a global unicast
  address — one private answer poisons the whole name;
- every redirect hop is re-resolved and re-validated against the same rules;
- the connection is **pinned to the validated address** (default), while `Host`
  and TLS SNI keep the provider hostname, so certificate verification still
  refers to the real name. A resolver that answers public during validation and
  private at connect time has no effect;
- ambient proxy settings are ignored, and keep-alive is off, because pooled
  connections are keyed by the pinned IP rather than the provider name;
- the body is streamed and bounded, and non-text payloads are refused.

Residual risk: `pin_addresses=False` exists for fixtures and must never be set
in production. Pinning is unit-tested at the request level and exercised over a
real loopback socket, but no live TLS handshake is performed by the automated
suite, so a deployment smoke test is still required before relying on it.

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
from urllib.parse import urljoin, urlsplit, urlunsplit

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
    # Connect to the address that was validated instead of letting the HTTP
    # stack resolve the name a second time. Disable only for tests that need to
    # see the logical hostname at the transport layer.
    pin_addresses: bool = True

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
    #: Final-response headers (G14): adapters need ETag / x-ratelimit-* /
    #: Retry-After to do conditional requests and honor rate limits. Stored
    #: as-is so multi-value headers survive; default keeps old constructors
    #: (tests, earlier callers) valid.
    headers: tuple[tuple[str, str], ...] = ()

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
                   *, allow_private: bool = False) -> list[str]:
    """Resolve, validate **every** answer, and return them for pinning."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not allow_private and not is_public_address(host):
            raise EgressError(f"IP literal '{host}' is not a public address")
        return [host]
    try:
        addresses = resolver(host, port)
    except EgressError:
        raise
    except Exception as exc:  # noqa: BLE001 — DNS failure is a policy failure
        raise EgressError(f"could not resolve host '{host}': {exc}") from None
    if not addresses:
        raise EgressError(f"could not resolve host '{host}': no addresses")
    if allow_private:
        return list(addresses)
    non_public = [address for address in addresses if not is_public_address(address)]
    if non_public:
        raise EgressError(
            f"host '{host}' resolves to a non-public address ({', '.join(non_public)}); refused"
        )
    return list(addresses)


def _netloc(host: str, port: int, scheme: str) -> str:
    """Bracket IPv6 literals and omit a default port."""
    bare = f"[{host}]" if ":" in host else host
    default = 443 if scheme.lower() == "https" else 80
    return bare if port == default else f"{bare}:{port}"


def _pinned_url(url: str, address: str) -> str:
    """Same path/query, but the socket goes to `address`."""
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    return urlunsplit((parts.scheme, _netloc(address, port, parts.scheme),
                       parts.path, parts.query, parts.fragment))


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
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
) -> FetchResult:
    """Fetch one provider page through the egress policy.

    Redirects are followed manually so every hop is validated. A non-2xx final
    status is returned to the caller rather than raised. `before_request` runs
    per hop so a caller can apply per-host politeness delays. `headers` are
    merged onto every hop (the validated `Host` always wins) and `params` are
    applied to the first hop only.
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
            # Ambient proxy settings would bypass address pinning, and pooled
            # connections are keyed by the pinned IP, so two provider names on
            # one address could otherwise share a TLS session.
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=0, max_connections=10),
        )

    requested = str(url)
    current = requested
    redirects: list[str] = []
    try:
        first_hop = True
        for _ in range(policy.max_redirects + 1):
            host, port = validate_url(current, policy)
            addresses = _resolve_public(
                host, port, resolver, allow_private=policy.allow_private,
            )
            if policy.pin_addresses:
                # Connect to the address we just validated. The hostname stays
                # in Host and in SNI, so HTTP authority and certificate
                # verification still refer to the provider, while a resolver
                # that changes its answer at connect time has no effect.
                target = _pinned_url(current, addresses[0])
                request_headers = {"Host": _netloc(host, port, urlsplit(current).scheme)}
                if headers:
                    request_headers.update(headers)
                extensions = {"sni_hostname": host}
            else:
                target, request_headers, extensions = current, headers or {}, {}
            if before_request is not None:
                before_request(current)

            stream_kwargs: dict = {}
            if first_hop:
                first_hop = False
                if params:
                    stream_kwargs["params"] = params

            with client.stream(
                "GET", target, headers=request_headers,
                extensions=extensions, **stream_kwargs,
            ) as response:
                status = response.status_code
                if status in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise EgressError(f"redirect {status} without a location header")
                    # Resolve against the logical URL: a relative Location must
                    # not inherit the pinned IP as the new hostname.
                    current = urljoin(current, location)
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
                    final_url=current,
                    status=status,
                    content_type=content_type,
                    body=b"".join(chunks),
                    redirects=tuple(redirects),
                    fetched_at=fetched_at,
                    headers=tuple(response.headers.items()),
                )
        raise EgressError(
            f"too many redirects (limit {policy.max_redirects})"
        )
    finally:
        if own_client:
            client.close()
