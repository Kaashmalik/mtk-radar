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
    """routes: url -> (status, headers, body) or callable(request)."""

    def handler(request):
        target = str(request.url)
        result = routes.get(target)
        if result is None:
            return httpx.Response(404, text="missing", request=request)
        status, headers, body = result
        return httpx.Response(status, headers=headers, content=body, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


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
            def fetch(self, url):
                return httpx.Response(
                    200, text="<p>collector excerpt</p>",
                    request=httpx.Request("GET", url),
                )

        item = fetch_page_snapshot("https://example.com/t", fetcher=Fetcher())[0]
        assert item.extra == {}
