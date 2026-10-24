"""Sectioned extraction (WP01 slice 8): every section, disagreements kept."""

import extractors
from document_sections import split_sections
from extractors import extract_document

URL = "https://example.com/terms"


def test_every_section_is_passed_to_the_extractor(monkeypatch):
    seen = []

    def fake(text, url, **kwargs):
        seen.append(text)
        return {}, [], None

    monkeypatch.setattr(extractors, "extract", fake)
    document = "Conditions apply. " * 500
    expected = split_sections(document, 200)
    fields, conflicts, model, total = extract_document(document, URL, max_chars=200)
    assert seen == [section.text for section in expected]
    assert total == len(expected)
    assert fields == {} and conflicts == [] and model is None


def test_short_document_extracts_as_before():
    text = "students only. Use code SAVE2026 at checkout. Valid until 31 December 2026."
    fields, conflicts, model, total = extract_document(text, URL)
    assert total == 1
    assert fields["promo_code"]["value"] == "SAVE2026"
    assert fields["eligibility"]["value"] == "students"
    assert conflicts == []
    assert model is None


def test_claim_found_in_a_later_section_is_still_extracted():
    document = ("Introductory filler. " * 400) + "\n\nUse code SAVE2026 at checkout."
    fields, _, _, total = extract_document(document, URL, max_chars=1000)
    assert total > 1
    assert fields["promo_code"]["value"] == "SAVE2026"


def test_disagreement_between_sections_is_a_conflict_not_a_choice():
    document = "Use code SAVE2026 at checkout.\n\nUse code SAVE30 at checkout."
    fields, conflicts, _, total = extract_document(document, URL, max_chars=40)
    assert total == 2
    # The first value is kept for display, never the more attractive one.
    assert fields["promo_code"]["value"] == "SAVE2026"
    promo_conflicts = [item for item in conflicts if item.get("field") == "promo_code"]
    assert len(promo_conflicts) == 1
    assert promo_conflicts[0]["reason"] == "document sections disagree"
    assert promo_conflicts[0]["sections"] == [0, 1]


def test_agreement_between_sections_is_not_a_conflict():
    document = (
        "Use code SAVE2026 at checkout.\n\n"
        "Students only. Use code SAVE2026 at checkout."
    )
    _, conflicts, _, total = extract_document(document, URL, max_chars=50)
    assert total == 2
    assert not [item for item in conflicts if item.get("field") == "promo_code"]


def test_exclusions_from_later_sections_are_not_lost():
    document = (
        "Available worldwide for students.\n\n"
        "Available worldwide, except in Cuba and Iran, for students."
    )
    fields, _, _, _ = extract_document(document, URL, max_chars=80)
    assert fields["regions"]["value"] == "worldwide"
    assert fields["regions"]["excluded_regions"] == ["Cuba", "Iran"]
