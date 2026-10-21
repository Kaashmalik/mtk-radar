"""Strict request contracts and URL identity checks for WP01."""

import uuid

import pytest
from pydantic import ValidationError

from document_sections import MAX_DOCUMENT_CHARS, MAX_SECTION_CHARS, SECTIONS_VERSION
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


@pytest.mark.parametrize("text", ["", " \n ", "bad\x00text", "x" * (MAX_DOCUMENT_CHARS + 1)],
                         ids=["empty", "blank", "nul", "oversized"])
def test_snapshot_must_be_bounded_valid_text(text):
    with pytest.raises(ValidationError):
        EvidenceIn(url="https://example.com/terms", captured_content=text)


def test_long_document_is_accepted_for_sectioned_extraction():
    """250k was the old refusal; sections replace truncation (WP01 slice 8)."""
    text = "Conditions apply to students only. Use code SAVE2026 at checkout.\n\n" * 4000
    assert len(text) > 250_000
    parsed = EvidenceIn(url="https://example.com/terms", captured_content=text)
    assert parsed.captured_content == text


def coverage(**overrides):
    base = {
        "version": SECTIONS_VERSION,
        "sections_total": 3,
        "max_section_chars": MAX_SECTION_CHARS,
        "evidence_ids": [str(uuid.uuid4())],
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("override", [
    {"version": "paragraph-groups"},
    {"sections_total": -1},
    {"sections_total": 100_001},
    {"max_section_chars": 99},
    {"evidence_ids": []},
    {"evidence_ids": ["not-a-uuid"]},
    {"truncated": True},
])
def test_invalid_coverage_rejected(override):
    with pytest.raises(ValidationError):
        ExtractionIn.model_validate({"fields": {}, "coverage": coverage(**override)})


def test_valid_coverage_accepted():
    parsed = ExtractionIn.model_validate({"fields": {}, "coverage": coverage()})
    assert parsed.coverage is not None
    assert parsed.coverage.sections_total == 3


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
