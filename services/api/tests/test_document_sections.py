"""Versioned section splitting (WP01 slice 8): bounded, contiguous, lossless."""

import pytest

from document_sections import (
    MAX_SECTION_CHARS,
    SECTIONS_VERSION,
    section_count,
    split_sections,
)


def test_versioned_rule():
    assert SECTIONS_VERSION == "paragraph-groups/1"


def test_empty_document_has_no_sections():
    assert split_sections("") == []


def test_short_document_is_one_whole_section():
    text = "Free trial for students. Use code SAVE2026."
    sections = split_sections(text)
    assert len(sections) == 1
    assert sections[0].text == text
    assert (sections[0].start, sections[0].end) == (0, len(text))


def test_paragraphs_are_grouped_within_the_ceiling():
    first = "A" * 400
    second = "B" * 400
    text = first + "\n\n" + second
    sections = split_sections(text, 1000)
    assert len(sections) == 1
    assert sections[0].text == text


def test_paragraphs_split_between_boundaries_when_they_do_not_fit():
    first = "A" * 600
    second = "B" * 600
    text = first + "\n\n" + second
    sections = split_sections(text, 1000)
    assert len(sections) == 2
    assert sections[0].text == first + "\n\n"
    assert sections[1].text == second


def test_oversized_paragraph_is_cut_after_a_sentence():
    text = "Sentence number one is here. " * 100
    sections = split_sections(text, 500)
    assert len(sections) > 1
    assert all(len(section.text) <= 500 for section in sections)
    assert "".join(section.text for section in sections) == text
    assert sections[0].text.rstrip().endswith(".")


def test_unbroken_text_falls_back_to_a_hard_cut():
    text = "x" * 2500
    sections = split_sections(text, 500)
    assert all(len(section.text) <= 500 for section in sections)
    assert "".join(section.text for section in sections) == text


def test_long_document_is_lossless_and_bounded():
    paragraph = "Eligibility applies to students only. " * 200
    text = "\n\n".join([paragraph] * 3)
    sections = split_sections(text, 1000)
    assert len(sections) > 1
    assert "".join(section.text for section in sections) == text
    assert all(len(section.text) <= 1000 for section in sections)
    assert [section.index for section in sections] == list(range(len(sections)))
    assert all(section.text for section in sections)


def test_sections_are_contiguous():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    sections = split_sections(text, 20)
    assert sections[0].start == 0
    for previous, current in zip(sections, sections[1:]):
        assert previous.end == current.start
    assert sections[-1].end == len(text)


def test_default_ceiling_stays_inside_the_llm_prompt():
    text = "word " * 100_000
    sections = split_sections(text)
    assert all(len(section.text) <= MAX_SECTION_CHARS for section in sections)
    assert MAX_SECTION_CHARS < 8000


def test_section_count_matches_split():
    text = "Conditions apply.\n\n" * 500
    assert section_count(text, 300) == len(split_sections(text, 300))


def test_splitting_is_deterministic():
    text = "A sentence. " * 900
    first = [(s.index, s.start, s.end) for s in split_sections(text, 700)]
    second = [(s.index, s.start, s.end) for s in split_sections(text, 700)]
    assert first == second


@pytest.mark.parametrize("max_chars", [0, 1, -5])
def test_absurd_ceiling_is_refused(max_chars):
    with pytest.raises(ValueError, match="at least 2"):
        split_sections("some text", max_chars)
