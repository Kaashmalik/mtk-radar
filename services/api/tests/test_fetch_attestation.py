"""Signed fetch provenance (WP01 slice 7): canonical form and HMAC.

Pure unit tests — no database, no network.
"""

import json
import uuid

import pytest

from fetch_attestation import (
    MIN_KEY_CHARS,
    canonical_provenance,
    sign_provenance,
    verify_provenance,
)
from schemas import EvidenceIn

KEY = "test-signing-key-0123456789abcdef0123456789abcdef"
OTHER_KEY = "another-signing-key-0123456789abcdef0123456789"


def payload(**overrides):
    base = {
        "requested_url": "https://example.com/terms",
        "final_url": "https://example.com/terms",
        "http_status": 200,
        "content_type": "text/html",
        "fetched_at": "2026-10-21T12:00:00+00:00",
        "redirects": [],
        "raw_sha256": "a" * 64,
        "parser_version": "page_watch/1",
        "fetch_identity": "verification-worker",
        "encoding": "utf-8",
        "robots": {
            "robots_url": "https://example.com/robots.txt",
            "checked_at": "2026-10-21T11:59:00+00:00",
            "allowed": True,
            "status": 200,
        },
    }
    base.update(overrides)
    return base


class TestCanonicalForm:
    def test_is_stable_across_key_order(self):
        reordered = dict(reversed(list(payload().items())))
        assert canonical_provenance(payload()) == canonical_provenance(reordered)

    def test_unknown_fields_are_not_covered(self):
        base = payload()
        extra = {**base, "byte_length": 1234, "note": "untrusted"}
        assert canonical_provenance(base) == canonical_provenance(extra)

    def test_urls_are_normalised(self):
        canonical = canonical_provenance(payload(
            requested_url="HTTPS://Example.COM:443",
            final_url="HTTPS://Example.COM:443/terms#fragment",
        ))
        material = json.loads(canonical)
        assert material["requested_url"] == "https://example.com/"
        assert material["final_url"] == "https://example.com/terms"

    def test_redirects_are_normalised_in_order(self):
        canonical = canonical_provenance(payload(redirects=[
            "https://example.com:443/one", "https://EXAMPLE.com/two",
        ]))
        assert json.loads(canonical)["redirects"] == [
            "https://example.com/one", "https://example.com/two",
        ]
        reversed_hops = canonical_provenance(payload(redirects=[
            "https://example.com/two", "https://example.com/one",
        ]))
        assert canonical != reversed_hops

    def test_timestamps_are_utc(self):
        utc = canonical_provenance(payload(fetched_at="2026-10-21T12:00:00+00:00"))
        offset = canonical_provenance(payload(fetched_at="2026-10-21T14:00:00+02:00"))
        zulu = canonical_provenance(payload(fetched_at="2026-10-21T12:00:00Z"))
        assert utc == offset == zulu
        assert json.loads(utc)["fetched_at"] == "2026-10-21T12:00:00+00:00"

    def test_naive_timestamps_are_not_signed_as_a_different_moment(self):
        material = json.loads(canonical_provenance(payload(fetched_at="2026-10-21T12:00:00")))
        assert material["fetched_at"] == ""

    def test_robots_decision_shape_is_fixed(self):
        material = json.loads(canonical_provenance(payload()))
        assert material["robots"] == {
            "robots_url": "https://example.com/robots.txt",
            "checked_at": "2026-10-21T11:59:00+00:00",
            "allowed": True,
            "status": 200,
        }


class TestSignature:
    def test_roundtrip(self):
        signature = sign_provenance(payload(), KEY)
        assert len(signature) == 64
        assert signature == signature.lower()
        assert verify_provenance(payload(), signature, KEY) is True

    def test_wrong_key_fails(self):
        signature = sign_provenance(payload(), KEY)
        assert verify_provenance(payload(), signature, OTHER_KEY) is False

    def test_tampering_each_signed_field_fails(self):
        signature = sign_provenance(payload(), KEY)
        tampered = {
            "raw_sha256": "b" * 64,
            "final_url": "https://evil.test/terms",
            "http_status": 404,
            "fetch_identity": "someone-else",
            "parser_version": "page_watch/2",
            "robots": {**payload()["robots"], "allowed": False},
            "fetched_at": "2026-10-21T12:00:01+00:00",
        }
        for field_name, value in tampered.items():
            assert verify_provenance(
                payload(**{field_name: value}), signature, KEY,
            ) is False, field_name

    def test_missing_or_garbage_signature_fails(self):
        assert verify_provenance(payload(), None, KEY) is False
        assert verify_provenance(payload(), "", KEY) is False
        assert verify_provenance(payload(), "0" * 64, KEY) is False

    def test_uppercase_signature_is_accepted(self):
        signature = sign_provenance(payload(), KEY)
        assert verify_provenance(payload(), signature.upper(), KEY) is True

    def test_short_key_is_refused(self):
        with pytest.raises(ValueError, match=str(MIN_KEY_CHARS)):
            sign_provenance(payload(), "short")
        assert verify_provenance(payload(), "0" * 64, "short") is False

    def test_signature_covers_the_parsed_model(self):
        """The API verifies the pydantic model, not the raw JSON dict."""
        raw = payload()
        body = b"<html>terms</html>"
        import base64
        import hashlib
        evidence = EvidenceIn.model_validate({
            "url": raw["final_url"],
            "source_id": str(uuid.uuid4()),
            "captured_content": "terms",
            "official": True,
            "raw_content_b64": base64.b64encode(body).decode("ascii"),
            "provenance": {**raw, "raw_sha256": hashlib.sha256(body).hexdigest()},
        })
        signature = sign_provenance(evidence.provenance, KEY)
        assert verify_provenance(evidence.provenance, signature, KEY) is True
        assert canonical_provenance(evidence.provenance) == canonical_provenance({
            **raw, "raw_sha256": hashlib.sha256(body).hexdigest(),
        })
