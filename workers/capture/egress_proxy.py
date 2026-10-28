"""Pinning egress proxy for the page-capture browser (review fix, SSRF).

Playwright's `context.route` sees only the FIRST URL of a redirect chain and
Chromium resolves DNS itself, so a public page could still reach a private
address through a redirect hop (iframe → 302 → 169.254.169.254) or a DNS
answer that changes between our check and Chromium's lookup (rebinding).

All browser traffic therefore goes through this local CONNECT proxy:
- only `CONNECT host:443` is accepted (https only; plain-HTTP proxying,
  other ports and every other method are refused with 403);
- the proxy resolves the host itself, requires EVERY answer to be a public
  address, and connects to exactly that validated address — the browser
  never resolves DNS, so redirects, sub-resources, iframes, websockets and
  rebinding all pass through the same check;
- bounded: connect timeout, idle timeout, and the proxy listens on
  loopback only for the lifetime of one capture.

Chromium must be launched with `proxy={"server": proxy.url}` and
`--proxy-bypass-list=<-loopback>` so even loopback targets are proxied
(and refused) instead of bypassing the proxy.
"""

from __future__ import annotations

import logging
import select
import socket
import socketserver
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

_PACKAGES = Path(__file__).resolve().parents[2] / "packages"
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from source_adapters.egress import (  # noqa: E402
    EgressError,
    _default_resolver,
    _resolve_public,
)

log = logging.getLogger("page_capture.proxy")

ALLOWED_PORTS = frozenset({443})
CONNECT_TIMEOUT_S = 10.0
IDLE_TIMEOUT_S = 30.0
MAX_HEADER_BYTES = 16 * 1024


def authorize(target: str, resolver: Callable[[str, int], list[str]],
              *, allow_private: bool = False) -> tuple[str, int]:
    """`host:port` from a CONNECT line → (validated address, port).

    Raises EgressError when the target must not be reached.
    """
    host, sep, port_text = target.rpartition(":")
    if not sep or not host:
        raise EgressError("CONNECT target must be host:port")
    host = host.strip("[]")
    try:
        port = int(port_text)
    except ValueError:
        raise EgressError("invalid CONNECT port") from None
    if port not in ALLOWED_PORTS:
        raise EgressError(f"port {port} refused (https/443 only)")
    addresses = _resolve_public(host, port, resolver, allow_private=allow_private)
    return addresses[0], port


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        client: socket.socket = self.request
        client.settimeout(IDLE_TIMEOUT_S)
        try:
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = client.recv(4096)
                if not chunk:
                    return
                head += chunk
                if len(head) > MAX_HEADER_BYTES:
                    return self._refuse(client, "request header too large")
            request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
            parts = request_line.split()
            if len(parts) != 3 or parts[0].upper() != "CONNECT":
                return self._refuse(client, "only CONNECT (https) is proxied")
            try:
                address, port = authorize(parts[1], self.server.resolver,
                                          allow_private=self.server.allow_private)
            except EgressError as exc:
                self.server.refused.append(parts[1])
                return self._refuse(client, str(exc))
            try:
                upstream = socket.create_connection((address, port), timeout=CONNECT_TIMEOUT_S)
            except OSError as exc:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                log.debug("upstream connect failed for %s: %s", parts[1], exc)
                return
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            # Bytes the client sent after the CONNECT header belong upstream.
            leftover = head.split(b"\r\n\r\n", 1)[1]
            if leftover:
                upstream.sendall(leftover)
            self._relay(client, upstream)
        except OSError:
            return

    @staticmethod
    def _refuse(client: socket.socket, reason: str) -> None:
        body = reason.encode("utf-8", "replace")[:300]
        client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\n"
                       b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)

    @staticmethod
    def _relay(a: socket.socket, b: socket.socket) -> None:
        sockets = [a, b]
        try:
            while True:
                readable, _, broken = select.select(sockets, [], sockets, IDLE_TIMEOUT_S)
                if broken or not readable:
                    return
                for src in readable:
                    data = src.recv(65536)
                    if not data:
                        return
                    (b if src is a else a).sendall(data)
        finally:
            b.close()


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class EgressProxy:
    """Loopback CONNECT proxy for one capture: `with EgressProxy() as p:`."""

    def __init__(self, resolver: Optional[Callable[[str, int], list[str]]] = None,
                 *, allow_private: bool = False):
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.resolver = resolver or _default_resolver
        self._server.allow_private = allow_private
        self._server.refused = []
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        name="page-capture-proxy", daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def refused(self) -> list[str]:
        return list(self._server.refused)

    def __enter__(self) -> "EgressProxy":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
