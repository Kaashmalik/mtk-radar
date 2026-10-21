"""Strict request contracts and URL identity checks for WP01."""

import uuid

import pytest
from pydantic import ValidationError

from schemas import EvidenceIn, ExtractionIn
from verification_checks import domain_matches


def field():
    return {
        "value": "students", "evidence_id": str(uuid.uuid4()),
        "evidence_url": "https://example.com/terms", "excerpt": "Verified students only.",
    }


@pytest.mark.parametrize("override", [
    {"value": True}, {"value": {}}, {"value": " "}, {"excerpt": ""}, {"excerpt": "bad\x00quote"},
    {"evidence_id": "invented"}, {"evidence_url": "http://example.com/terms"},
    {"evidence_url": "https://user:secret@example.com/terms"},
    {"evidence_url": "https://example.com/terms#claim"},
    {"confidence": float("nan")}, {"confidence": 1.01}, {"run_command": "anything"},
])
def test_invalid_fields_rejected(override):
    with pytest.raises(ValidationError):
        ExtractionIn.model_validate({"fields": {"eligibility": {**field(), **override}}})


def test_unknown_field_and_extra_control_flags_rejected():
    for payload in ({"fields": {"admin_approved": field()}}, {"force_verify": True}, {"complete": "true"}):
        with pytest.raises(ValidationError):
            ExtractionIn.model_validate(payload)


@pytest.mark.parametrize("text", ["", " \n ", "bad\x00text", "x" * 250_001],
                         ids=["empty", "blank", "nul", "oversized"])
def test_snapshot_must_be_bounded_valid_text(text):
    with pytest.raises(ValidationError):
        EvidenceIn(url="https://example.com/terms", captured_content=text)


@pytest.mark.parametrize("url,expected", [
    ("https://example.com/terms", True), ("https://cdn.example.com/terms", True),
    ("https://EXAMPLE.com:443/terms", True), ("https://example.com.evil.test", False),
    ("https://notexample.com", False), ("http://example.com", False),
    ("https://secret@example.com", False), ("https://example.com:8080", False),
    ("https://example.com:bad", False),
])
def test_domain_boundary_and_transport(url, expected):
    assert domain_matches(url, ["example.com"]) is expected


def test_idn_domain_normalization():
    assert domain_matches("https://xn--bcher-kva.example/terms", ["bücher.example"])
    assert not domain_matches("https://other.example", ["https://other.example"])
