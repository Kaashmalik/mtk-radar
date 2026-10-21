"""Raw-byte and fetch-provenance contracts (WP01 slice 3).

These are pure schema checks: no database, no network.
"""

import base64
import hashlib
import uuid

import pytest
from pydantic import ValidationError

from schemas import EvidenceIn

BODY = b"<html><title>Terms</title><p>Free for students.</p></html>"
RAW_B64 = base64.b64encode(BODY).decode("ascii")
RAW_SHA = hashlib.sha256(BODY).hexdigest()


def provenance(**overrides):
    base = {
        "requested_url": "https://example.com/terms",
        "final_url": "https://example.com/terms",
        "http_status": 200,
        "content_type": "text/html",
        "fetched_at": "2026-10-21T12:00:00+00:00",
        "redirects": [],
        "raw_sha256": RAW_SHA,
        "parser_version": "page_watch/1",
        "fetch_identity": "verification-worker",
        "signature": "a" * 64,
        "robots": {
            "robots_url": "https://example.com/robots.txt",
            "checked_at": "2026-10-21T11:59:00+00:00",
            "allowed": True,
            "status": 200,
        },
    }
    base.update(overrides)
    return base


def evidence(**overrides):
    base = {
        "url": "https://example.com/terms",
        "source_id": str(uuid.uuid4()),
        "captured_content": "Free for students.",
        "official": True,
        "raw_content_b64": RAW_B64,
        "provenance": provenance(),
    }
    base.update(overrides)
    return base


class TestRawSnapshot:
    def test_valid_raw_snapshot_accepted(self):
        parsed = EvidenceIn.model_validate(evidence())
        assert parsed.raw_content_b64 == RAW_B64

    def test_invalid_base64_rejected(self):
        with pytest.raises(ValidationError, match="valid base64"):
            EvidenceIn.model_validate(evidence(raw_content_b64="not base64!!"))

    def test_empty_raw_snapshot_rejected(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            EvidenceIn.model_validate(evidence(raw_content_b64=""))

    def test_oversized_raw_snapshot_rejected(self):
        too_big = base64.b64encode(b"x" * 2_000_001).decode("ascii")
        with pytest.raises(ValidationError, match="2,000,000-byte"):
            EvidenceIn.model_validate(evidence(raw_content_b64=too_big))

    def test_provenance_without_raw_bytes_rejected(self):
        with pytest.raises(ValidationError, match="provenance requires raw_content_b64"):
            EvidenceIn.model_validate(evidence(raw_content_b64=None))


class TestProvenance:
    def test_valid_provenance_accepted(self):
        parsed = EvidenceIn.model_validate(evidence())
        assert parsed.provenance.parser_version == "page_watch/1"
        assert parsed.provenance.redirects == []

    def test_bad_hash_shape_rejected(self):
        with pytest.raises(ValidationError):
            EvidenceIn.model_validate(evidence(provenance=provenance(raw_sha256="abc")))

    def test_http_status_bounds_enforced(self):
        with pytest.raises(ValidationError):
            EvidenceIn.model_validate(evidence(provenance=provenance(http_status=42)))
        with pytest.raises(ValidationError):
            EvidenceIn.model_validate(evidence(provenance=provenance(http_status=600)))

    def test_redirect_chain_is_bounded(self):
        chain = [f"https://example.com/r{i}" for i in range(11)]
        with pytest.raises(ValidationError):
            EvidenceIn.model_validate(evidence(provenance=provenance(redirects=chain)))

    def test_parser_version_required(self):
        with pytest.raises(ValidationError):
            EvidenceIn.model_validate(evidence(provenance=provenance(parser_version="")))

    def test_legacy_evidence_without_provenance_still_valid(self):
        parsed = EvidenceIn.model_validate(evidence(
            raw_content_b64=None, provenance=None,
        ))
        assert parsed.provenance is None


class TestRobotsDecision:
    """WP01 slice 6: permission travels with the fetch it allowed."""

    def test_allowed_robots_decision_parsed(self):
        parsed = EvidenceIn.model_validate(evidence())
        assert parsed.provenance.robots.allowed is True
        assert parsed.provenance.robots.status == 200
        assert str(parsed.provenance.robots.robots_url) == "https://example.com/robots.txt"

    def test_robots_without_raw_bytes_rejected(self):
        with pytest.raises(ValidationError, match="provenance requires raw_content_b64"):
            EvidenceIn.model_validate(evidence(raw_content_b64=None))

    def test_allowed_decision_cannot_hide_a_server_error(self):
        with pytest.raises(ValidationError, match="readable robots.txt"):
            EvidenceIn.model_validate(evidence(provenance=provenance(robots={
                "robots_url": "https://example.com/robots.txt",
                "checked_at": "2026-10-21T11:59:00+00:00",
                "allowed": True,
                "status": 503,
            })))

    def test_allowed_decision_cannot_be_auth_wall_or_ratelimit(self):
        for status in (401, 403, 429):
            with pytest.raises(ValidationError, match="readable robots.txt"):
                EvidenceIn.model_validate(evidence(provenance=provenance(robots={
                    "robots_url": "https://example.com/robots.txt",
                    "checked_at": "2026-10-21T11:59:00+00:00",
                    "allowed": True,
                    "status": status,
                })))

    def test_allowed_decision_requires_a_status(self):
        with pytest.raises(ValidationError, match="readable robots.txt"):
            EvidenceIn.model_validate(evidence(provenance=provenance(robots={
                "robots_url": "https://example.com/robots.txt",
                "checked_at": "2026-10-21T11:59:00+00:00",
                "allowed": True,
                "status": None,
            })))

    def test_disallowed_decision_remains_representable(self):
        """A refusal is a valid record; the API rejects it as evidence later."""
        parsed = EvidenceIn.model_validate(evidence(provenance=provenance(robots={
            "robots_url": "https://example.com/robots.txt",
            "checked_at": "2026-10-21T11:59:00+00:00",
            "allowed": False,
            "status": 403,
        })))
        assert parsed.provenance.robots.allowed is False

    def test_robots_url_must_be_a_url(self):
        with pytest.raises(ValidationError):
            EvidenceIn.model_validate(evidence(provenance=provenance(robots={
                "robots_url": "not a url",
                "checked_at": "2026-10-21T11:59:00+00:00",
                "allowed": True,
                "status": 200,
            })))


class TestSignatureShape:
    """WP01 slice 7: the signature is 64 lower-case hex characters or absent."""

    def test_valid_signature_accepted(self):
        parsed = EvidenceIn.model_validate(evidence())
        assert parsed.provenance.signature == "a" * 64

    def test_signature_is_optional_at_the_schema_level(self):
        """Legacy callers may omit it; the API rejects them when required."""
        parsed = EvidenceIn.model_validate(evidence(provenance=provenance(signature=None)))
        assert parsed.provenance.signature is None

    def test_non_hex_signature_rejected(self):
        with pytest.raises(ValidationError):
            EvidenceIn.model_validate(evidence(provenance=provenance(signature="g" * 64)))

    def test_wrong_length_signature_rejected(self):
        with pytest.raises(ValidationError):
            EvidenceIn.model_validate(evidence(provenance=provenance(signature="a" * 63)))
