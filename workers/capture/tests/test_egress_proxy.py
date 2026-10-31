"""Pinning CONNECT proxy (review fix): redirects/rebinding cannot reach
private networks because the proxy resolves and connects itself."""

import socket
import threading

import pytest

from egress_proxy import EgressProxy, authorize
from source_adapters.egress import EgressError

TABLE = {"example.org": ["93.184.215.14"], "rebind.example": ["93.184.215.14", "10.0.0.7"],
         "metadata.internal": ["169.254.169.254"], "localhost": ["127.0.0.1"]}


def resolver(host, port):
    if host not in TABLE:
        raise OSError("NXDOMAIN")
    return TABLE[host]


def test_authorize_pins_public_https_targets_only():
    assert authorize("example.org:443", resolver) == ("93.184.215.14", 443)
    for target, why in [("example.org:80", "port"), ("example.org:22", "port"),
                        ("metadata.internal:443", "non-public"),
                        ("rebind.example:443", "non-public"),  # ANY private answer refuses
                        ("10.0.0.5:443", "public"), ("127.0.0.1:443", "public"),
                        ("nohost", "host:port"), ("nxdomain.test:443", "resolve")]:
        with pytest.raises(EgressError, match=why):
            authorize(target, resolver)


def _send(proxy_url, payload: bytes) -> bytes:
    host, port = proxy_url.replace("http://", "").split(":")
    with socket.create_connection((host, int(port)), timeout=5) as sock:
        sock.sendall(payload)
        return sock.recv(4096)


def test_proxy_refuses_private_targets_and_non_connect_requests_on_the_wire():
    with EgressProxy(resolver) as proxy:
        refused = _send(proxy.url, b"CONNECT metadata.internal:443 HTTP/1.1\r\n\r\n")
        assert refused.startswith(b"HTTP/1.1 403")
        plain = _send(proxy.url, b"GET http://example.org/ HTTP/1.1\r\nHost: example.org\r\n\r\n")
        assert plain.startswith(b"HTTP/1.1 403") and b"only CONNECT" in plain
        assert proxy.refused == ["metadata.internal:443"]


def test_proxy_tunnels_to_the_validated_address(monkeypatch):
    """The upstream connection goes to the address the proxy validated —
    the client never resolves DNS (no rebinding window)."""
    upstream = socket.socket()
    upstream.bind(("127.0.0.1", 0))
    upstream.listen(1)
    up_port = upstream.getsockname()[1]
    connected_to = []
    real_create = socket.create_connection

    def create_connection(address, timeout=None):
        connected_to.append(address)
        return real_create(("127.0.0.1", up_port), timeout=timeout)

    import egress_proxy
    monkeypatch.setattr(egress_proxy.socket, "create_connection", create_connection)

    def echo():
        conn, _ = upstream.accept()
        conn.sendall(conn.recv(100).upper())
        conn.close()

    threading.Thread(target=echo, daemon=True).start()
    with EgressProxy(resolver) as proxy:
        host, port = proxy.url.replace("http://", "").split(":")
        with real_create((host, int(port)), timeout=5) as sock:
            sock.sendall(b"CONNECT example.org:443 HTTP/1.1\r\n\r\n")
            assert sock.recv(100).startswith(b"HTTP/1.1 200")
            sock.sendall(b"hello")
            assert sock.recv(100) == b"HELLO"
    assert connected_to == [("93.184.215.14", 443)], "pinned to the validated IP"
    upstream.close()
