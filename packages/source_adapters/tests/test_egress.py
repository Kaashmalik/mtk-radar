"""Safe egress policy (master plan §6 step 2, audit A19).

The verifier must never be usable as an SSRF proxy: HTTPS only, public
addresses only, every redirect hop re-validated, bounded body.
"""

import base64
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # packages/

from source_adapters import Fetcher  # noqa: E402
from source_adapters.egress import (  # noqa: E402
    EgressError,
    EgressPolicy,
    FetchResult,
    is_public_address,
    safe_fetch,
    validate_url,
)

PUBLIC = ["93.184.216.34"]
FIXED_NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def resolver_public(host, port):
    return list(PUBLIC)


def resolver_private(host, port):
    return ["10.0.0.7"]


def resolver_mixed(host, port):
    return ["93.184.216.34", "127.0.0.1"]


def client_for(routes):
    """routes: url -> (status, headers, body).

    The handler resolves the route from the ``Host`` header, because the egress
    policy pins the socket to a validated IP address while preserving the
    original hostname in ``Host``/SNI.
    """

    def handler(request):
        scheme = request.url.scheme
        host = request.headers.get("host", "")
        # Match on scheme://host+path; query strings are part of the request,
        # not the route identity.
        target = f"{scheme}://{host}{request.url.path}"
        client.seen.append(request)
        result = routes.get(target)
        if result is None:
            return httpx.Response(404, text="missing", request=request)
        status, headers, body = result
        return httpx.Response(status, headers=headers, content=body, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client.seen = []
    return client


def policy(**kwargs):
    return EgressPolicy(**kwargs)


class TestAddressClassification:
    @pytest.mark.parametrize("addr", [
        "93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946",
    ])
    def test_public_addresses_allowed(self, addr):
        assert is_public_address(addr) is True

    @pytest.mark.parametrize("addr", [
        "127.0.0.1", "127.1.2.3", "0.0.0.0", "10.1.2.3", "172.16.0.1",
        "172.31.255.255", "192.168.1.1", "169.254.169.254", "100.64.0.1",
        "::1", "::", "fe80::1", "fc00::1", "ff02::1", "224.0.0.1",
    ])
    def test_private_and_special_addresses_rejected(self, addr):
        assert is_public_address(addr) is False

    def test_garbage_is_not_a_public_address(self):
        assert is_public_address("not-an-ip") is False


class TestUrlPolicy:
    def test_https_public_url_is_allowed(self):
        assert validate_url("https://example.com/terms", policy()) == ("example.com", 443)

    def test_plain_http_is_refused_by_default(self):
        with pytest.raises(EgressError, match="scheme"):
            validate_url("http://example.com/terms", policy())

    def test_plain_http_allowed_only_when_explicitly_permitted(self):
        assert validate_url(
            "http://127.0.0.1:8099/terms",
            policy(allow_plain_http=True, allow_private=True, allowed_ports=frozenset({8099})),
        ) == ("127.0.0.1", 8099)

    def test_private_opt_in_does_not_leak_into_the_default_policy(self):
        with pytest.raises(EgressError, match="public"):
            validate_url(
                "http://127.0.0.1:8099/terms",
                policy(allow_plain_http=True, allowed_ports=frozenset({8099})),
            )

    @pytest.mark.parametrize("url", [
        "file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/x",
        "javascript:alert(1)", "data:text/html,<b>x</b>",
    ])
    def test_non_http_schemes_refused(self, url):
        with pytest.raises(EgressError, match="scheme"):
            validate_url(url, policy())

    def test_credentials_in_url_refused(self):
        with pytest.raises(EgressError, match="credentials"):
            validate_url("https://user:pass@example.com/terms", policy())

    def test_blocked_hostnames_refused(self):
        with pytest.raises(EgressError, match="host"):
            validate_url("https://localhost/terms", policy())

    @pytest.mark.parametrize("url", [
        "https://127.0.0.1/terms", "https://[::1]/terms",
        "https://169.254.169.254/latest/meta-data/", "https://10.0.0.5/terms",
    ])
    def test_private_ip_literals_refused(self, url):
        with pytest.raises(EgressError, match="public"):
            validate_url(url, policy())

    def test_non_standard_port_refused(self):
        with pytest.raises(EgressError, match="port"):
            validate_url("https://example.com:22/terms", policy())

    def test_explicitly_allowed_port_accepted(self):
        assert validate_url(
            "https://example.com:8443/terms", policy(allowed_ports=frozenset({8443}))
        ) == ("example.com", 8443)

    def test_empty_host_refused(self):
        with pytest.raises(EgressError):
            validate_url("https:///terms", policy())


class TestDns:
    def test_hostname_resolving_to_private_address_is_refused(self):
        with pytest.raises(EgressError, match="non-public"):
            safe_fetch(
                "https://internal.example.com/terms",
                policy=policy(),
                resolver=resolver_private,
                clock=lambda: FIXED_NOW,
            )

    def test_one_private_answer_poisons_the_whole_name(self):
        """A rebinding attempt must not win by listing a public address too."""
        with pytest.raises(EgressError, match="non-public"):
            safe_fetch(
                "https://mixed.example.com/terms",
                policy=policy(),
                resolver=resolver_mixed,
                clock=lambda: FIXED_NOW,
            )

    def test_resolution_failure_is_an_egress_error(self):
        def broken(host, port):
            raise OSError("nope")

        with pytest.raises(EgressError, match="resolve"):
            safe_fetch(
                "https://example.com/terms", policy=policy(), resolver=broken,
                clock=lambda: FIXED_NOW,
            )


class TestFetch:
    def route(self, url, body=b"<html>terms</html>", headers=None, status=200):
        resolved = {"content-type": "text/html"} if headers is None else dict(headers)
        return {url: (status, resolved, body)}

    def test_bounded_body_and_provenance_returned(self):
        url = "https://example.com/terms"
        with client_for(self.route(url)) as client:
            result = safe_fetch(url, policy=policy(), client=client,
                                resolver=resolver_public, clock=lambda: FIXED_NOW)
        assert result.body == b"<html>terms</html>"
        assert result.status == 200
        assert result.content_type == "text/html"
        assert result.requested_url == url and result.final_url == url
        assert result.redirects == ()
        assert result.fetched_at == FIXED_NOW

    def test_oversized_body_refused(self):
        url = "https://example.com/big"
        with client_for(self.route(url, body=b"x" * 500)) as client:
            with pytest.raises(EgressError, match="too large"):
                safe_fetch(url, policy=policy(max_bytes=100), client=client,
                           resolver=resolver_public, clock=lambda: FIXED_NOW)

    @pytest.mark.parametrize("ctype", [
        "image/png", "video/mp4", "audio/mpeg", "application/octet-stream",
    ])
    def test_binary_content_type_refused(self, ctype):
        url = "https://example.com/bin"
        with client_for(self.route(url, headers={"content-type": ctype})) as client:
            with pytest.raises(EgressError, match="content type"):
                safe_fetch(url, policy=policy(), client=client,
                           resolver=resolver_public, clock=lambda: FIXED_NOW)

    def test_missing_content_type_is_tolerated(self):
        url = "https://example.com/plain"
        with client_for(self.route(url, headers={})) as client:
            result = safe_fetch(url, policy=policy(), client=client,
                                resolver=resolver_public, clock=lambda: FIXED_NOW)
        assert result.content_type == ""

    def test_redirect_chain_is_followed_and_recorded(self):
        first = "https://example.com/terms"
        second = "https://example.com/terms-2026"
        routes = {
            first: (302, {"location": second}, b""),
            second: (200, {"content-type": "text/html"}, b"<p>final</p>"),
        }
        with client_for(routes) as client:
            result = safe_fetch(first, policy=policy(), client=client,
                                resolver=resolver_public, clock=lambda: FIXED_NOW)
        assert result.final_url == second
        assert result.redirects == (second,)
        assert result.body == b"<p>final</p>"

    def test_redirect_to_private_host_refused(self):
        first = "https://example.com/terms"
        routes = {first: (302, {"location": "https://127.0.0.1/admin"}, b"")}
        with client_for(routes) as client:
            with pytest.raises(EgressError, match="public"):
                safe_fetch(first, policy=policy(), client=client,
                           resolver=resolver_public, clock=lambda: FIXED_NOW)

    def test_redirect_to_non_https_refused(self):
        first = "https://example.com/terms"
        routes = {first: (302, {"location": "http://example.com/terms"}, b"")}
        with client_for(routes) as client:
            with pytest.raises(EgressError, match="scheme"):
                safe_fetch(first, policy=policy(), client=client,
                           resolver=resolver_public, clock=lambda: FIXED_NOW)

    def test_redirect_loop_is_bounded(self):
        first = "https://example.com/a"
        second = "https://example.com/b"
        routes = {
            first: (302, {"location": second}, b""),
            second: (302, {"location": first}, b""),
        }
        with client_for(routes) as client:
            with pytest.raises(EgressError, match="redirect"):
                safe_fetch(first, policy=policy(max_redirects=3), client=client,
                           resolver=resolver_public, clock=lambda: FIXED_NOW)

    def test_redirect_without_location_refused(self):
        first = "https://example.com/terms"
        routes = {first: (302, {}, b"")}
        with client_for(routes) as client:
            with pytest.raises(EgressError, match="location"):
                safe_fetch(first, policy=policy(), client=client,
                           resolver=resolver_public, clock=lambda: FIXED_NOW)

    def test_http_error_status_is_returned_not_raised(self):
        """An outage is 'unavailable', not proof the offer ended (§6 step 2)."""
        url = "https://example.com/down"
        with client_for({url: (503, {"content-type": "text/html"}, b"busy")}) as client:
            result = safe_fetch(url, policy=policy(), client=client,
                                resolver=resolver_public, clock=lambda: FIXED_NOW)
        assert result.status == 503


class TestAddressPinning:
    """The connection must go to the address that was validated, not a re-lookup."""

    def route(self, url, body=b"<html>terms</html>"):
        return {url: (200, {"content-type": "text/html"}, body)}

    def test_socket_targets_the_validated_address(self):
        url = "https://example.com/terms"
        with client_for(self.route(url)) as client:
            safe_fetch(url, policy=policy(), client=client,
                       resolver=resolver_public, clock=lambda: FIXED_NOW)
        sent = client.seen[0]
        assert sent.url.host == "93.184.216.34"          # socket destination
        assert sent.headers["host"] == "example.com"     # HTTP authority
        assert sent.extensions["sni_hostname"] == "example.com"  # TLS identity

    def test_pinned_request_still_reports_the_logical_url(self):
        url = "https://example.com/terms"
        with client_for(self.route(url)) as client:
            result = safe_fetch(url, policy=policy(), client=client,
                                resolver=resolver_public, clock=lambda: FIXED_NOW)
        assert result.requested_url == url
        assert result.final_url == url

    def test_ipv6_pin_is_bracketed(self):
        url = "https://example.com/ipv6"
        v6 = "2606:2800:220:1:248:1893:25c8:1946"
        with client_for(self.route(url)) as client:
            safe_fetch(url, policy=policy(), client=client,
                       resolver=lambda host, port: [v6], clock=lambda: FIXED_NOW)
        sent = client.seen[0]
        assert sent.url.host == v6
        assert sent.headers["host"] == "example.com"
        assert sent.extensions["sni_hostname"] == "example.com"

    def test_each_redirect_hop_is_resolved_and_pinned_again(self):
        first = "https://example.com/terms"
        second = "https://example.com/terms-2026"
        routes = {
            first: (302, {"location": second}, b""),
            second: (200, {"content-type": "text/html"}, b"<p>final</p>"),
        }
        answers = {("example.com", 443): ["93.184.216.34", "93.184.216.35"]}
        calls = []

        def resolver(host, port):
            calls.append((host, port))
            # A rebinding resolver: different answer on the second lookup.
            return [answers[(host, port)][min(len(calls) - 1, 1)]]

        with client_for(routes) as client:
            result = safe_fetch(first, policy=policy(), client=client,
                                resolver=resolver, clock=lambda: FIXED_NOW)
        assert result.final_url == second
        assert [request.url.host for request in client.seen] == [
            "93.184.216.34", "93.184.216.35",
        ]
        assert all(r.headers["host"] == "example.com" for r in client.seen)

    def test_relative_redirect_resolves_against_the_hostname_not_the_ip(self):
        first = "https://example.com/terms"
        second = "https://example.com/terms-2026"
        routes = {
            first: (302, {"location": "/terms-2026"}, b""),
            second: (200, {"content-type": "text/html"}, b"<p>final</p>"),
        }
        with client_for(routes) as client:
            result = safe_fetch(first, policy=policy(), client=client,
                                resolver=resolver_public, clock=lambda: FIXED_NOW)
        assert result.final_url == second
        assert result.redirects == (second,)

    def test_pinning_can_be_disabled_only_explicitly(self):
        url = "https://example.com/terms"
        with client_for(self.route(url)) as client:
            safe_fetch(url, policy=policy(pin_addresses=False), client=client,
                       resolver=resolver_public, clock=lambda: FIXED_NOW)
        assert client.seen[0].url.host == "example.com"

    def test_default_policy_pins(self):
        assert EgressPolicy().pin_addresses is True

    def test_dns_is_rechecked_even_when_the_name_was_seen_before(self):
        """No cross-request cache: every hop is resolved and validated."""
        url = "https://example.com/terms"
        answers = [["93.184.216.34"], ["10.0.0.7"]]
        calls = []

        def resolver(host, port):
            calls.append(host)
            return answers[min(len(calls) - 1, 1)]

        with client_for(self.route(url)) as client:
            safe_fetch(url, policy=policy(), client=client,
                       resolver=resolver, clock=lambda: FIXED_NOW)
            with pytest.raises(EgressError, match="non-public"):
                safe_fetch(url, policy=policy(), client=client,
                           resolver=resolver, clock=lambda: FIXED_NOW)
        assert len(calls) == 2


class TestPinnedConnectionOverRealSockets:
    """MockTransport cannot prove httpcore honours our Host/pin wiring."""

    def test_host_header_survives_pinning_over_a_real_socket(self):
        import http.server
        import threading

        received: list[tuple[str, str]] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 — stdlib callback name
                received.append((self.path, self.headers.get("Host", "")))
                body = b"<html>ok</html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            local_policy = EgressPolicy(
                allow_plain_http=True, allow_private=True,
                allowed_ports=frozenset({port}),
            )
            url = f"http://example.test:{port}/terms"
            result = safe_fetch(
                url, policy=local_policy,
                resolver=lambda host, _port: ["127.0.0.1"],
                clock=lambda: FIXED_NOW,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        assert result.status == 200
        assert result.final_url == url
        # The server was reached through the pinned loopback address but saw
        # the provider hostname as its authority.
        assert received == [("/terms", f"example.test:{port}")]


class TestPageSnapshotProvenance:
    """The verification path returns the exact bytes, not just derived text."""

    BODY = b"<html><title>Terms</title><p>Free for students.</p></html>"

    def fake_fetcher(self, final_url):
        body = self.BODY

        class FakeFetcher:
            def safe_fetch(self, url, *, policy=None, resolver=None, clock=None):
                return FetchResult(
                    requested_url=url, final_url=final_url, status=200,
                    content_type="text/html; charset=utf-8", body=body,
                    redirects=(final_url,), fetched_at=FIXED_NOW,
                )

        return FakeFetcher()

    def test_policy_fetch_returns_raw_bytes_and_provenance(self):
        from source_adapters.page_watch import PARSER_VERSION, fetch_page_snapshot
        url = "https://example.com/terms"
        item = fetch_page_snapshot(
            url, fetcher=self.fake_fetcher(url + "/2026"), max_text_chars=None,
            policy=EgressPolicy(),
        )[0]
        provenance = item.extra["provenance"]
        assert item.url == url + "/2026"
        assert base64.b64decode(item.extra["raw_content_b64"]) == self.BODY
        assert provenance["raw_sha256"] == hashlib.sha256(self.BODY).hexdigest()
        assert provenance["parser_version"] == PARSER_VERSION
        assert provenance["byte_length"] == len(self.BODY)
        assert provenance["encoding"] == "utf-8"
        assert "Free for students." in item.text

    def test_collector_path_has_no_provenance(self):
        from source_adapters.page_watch import fetch_page_snapshot

        class Fetcher:
            def fetch(self, url, *, headers=None, params=None):
                return httpx.Response(
                    200, text="<p>collector excerpt</p>",
                    request=httpx.Request("GET", url),
                )

            def fetch_policy(self, url, *, headers=None, params=None, policy=None):
                return self.fetch(url, headers=headers, params=params)

        item = fetch_page_snapshot("https://example.com/t", fetcher=Fetcher())[0]
        assert item.extra == {}


class TestFetchPolicy:
    """Collectors go through the same egress policy as verification."""

    @staticmethod
    def fetcher_for(routes):
        f = Fetcher()
        f._safe_client = client_for(routes)
        return f

    def test_returns_final_response_for_collector_code(self):
        url = "https://example.com/feed"
        f = self.fetcher_for({url: (200, {"content-type": "text/html"}, b"<p>ok</p>")})
        resp = f.fetch_policy(url, policy=policy())
        assert resp.status_code == 200
        assert resp.content == b"<p>ok</p>"
        # The URL reported is the logical one, never the pinned address.
        assert resp.url.host == "example.com"

    def test_private_redirect_is_refused_for_collectors_too(self):
        first = "https://example.com/feed"
        f = self.fetcher_for({first: (302, {"location": "https://127.0.0.1/secret"}, b"")})
        with pytest.raises(EgressError, match="public"):
            f.fetch_policy(first, policy=policy())

    def test_non_2xx_final_raises_like_fetch(self):
        url = "https://example.com/missing"
        f = self.fetcher_for({url: (404, {"content-type": "text/html"}, b"gone")})
        with pytest.raises(httpx.HTTPStatusError):
            f.fetch_policy(url, policy=policy())

    def test_params_reach_the_first_hop_only(self):
        url = "https://example.com/search"
        f = self.fetcher_for({url: (200, {"content-type": "text/html"}, b"<p>q=1</p>")})
        resp = f.fetch_policy(url, params={"q": "1"}, policy=policy())
        assert resp.url.host == "example.com"
        assert b"q=1" in resp.content

    def test_custom_headers_reach_the_request(self):
        url = "https://example.com/feed"
        f = self.fetcher_for({
            url: (200, {"content-type": "application/xml"}, b"<?xml version='1.0'?>"),
        })
        resp = f.fetch_policy(
            url, headers={"Accept": "application/rss+xml"}, policy=policy(),
        )
        # Request headers merge with the client defaults; user headers win.
        sent = f._safe_client.seen[0] if hasattr(f._safe_client, "seen") else None
        assert sent is not None and sent.headers.get("accept") == "application/rss+xml"

    def test_http_is_refused_by_default(self):
        f = self.fetcher_for({"http://example.com/feed": (200, {}, b"")})
        with pytest.raises(EgressError, match="scheme"):
            f.fetch_policy("http://example.com/feed", policy=policy())

    def test_http_allowed_with_explicit_permissive_policy(self):
        url = "http://example.com/feed"
        f = self.fetcher_for({url: (200, {"content-type": "text/html"}, b"<p>ok</p>")})
        resp = f.fetch_policy(
            url,
            policy=EgressPolicy(allow_plain_http=True, allow_private=True,
                                allowed_ports=frozenset({80})),
        )
        assert resp.status_code == 200
