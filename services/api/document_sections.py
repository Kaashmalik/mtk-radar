"""Versioned document sections (WP01 slice 8): bounded, lossless splitting.

Official terms pages can be far longer than a single model prompt. Truncating the
text silently drops conditions — often the restrictions that make an offer
inapplicable. This module splits a document into sections that are small enough
to examine completely, without changing a single character of the input.

Boundary rule, `paragraph-groups/1`:

- paragraphs are separated by a blank line; consecutive paragraphs are grouped
  while the group stays within :data:`MAX_SECTION_CHARS`;
- a single paragraph larger than the ceiling is cut at the last sentence end in
  the window (falling back to a word boundary, then a hard cut);
- sections are contiguous slices of the input, so joining them reproduces the
  text exactly. Coverage is therefore countable and verifiable: the API
  recomputes the number of sections from the stored snapshot text and rejects a
  record that claims fewer.

The API and the verification worker share this implementation, so a producer and
the verifier always agree on what "the whole document" means.

Changing a boundary rule changes every signature-adjacent count, so it is
versioned: extend :data:`SECTIONS_VERSION` when the rule changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

#: Bump when the boundary rule changes; the API rejects unknown versions.
SECTIONS_VERSION = "paragraph-groups/1"

#: Section ceiling. The optional LLM extractor sends one section per prompt and
#: currently truncates at 8,000 characters, so a section must stay below that.
MAX_SECTION_CHARS = 6000

#: Whole-document ceiling. Egress already stops a response above 2,000,000
#: bytes; a larger text is refused for review, never cut.
MAX_DOCUMENT_CHARS = 2_000_000

_PARAGRAPH_BREAK = re.compile(r"\n[ \t\r\f\v]*\n")


@dataclass(frozen=True)
class Section:
    """One contiguous slice of the document."""

    index: int
    text: str
    start: int
    end: int


def _paragraph_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    position = 0
    for match in _PARAGRAPH_BREAK.finditer(text):
        ranges.append((position, match.end()))
        position = match.end()
    ranges.append((position, len(text)))
    return [(start, end) for start, end in ranges if end > start]


def _split_oversized(text: str, start: int, end: int,
                     max_chars: int) -> list[tuple[int, int]]:
    """Cut one oversized paragraph into pieces, preferably after a sentence."""
    pieces: list[tuple[int, int]] = []
    position = start
    while end - position > max_chars:
        window = text[position:position + max_chars]
        cut = max(
            window.rfind(". "), window.rfind("! "),
            window.rfind("? "), window.rfind("\n"),
        )
        if cut < max_chars // 2:
            cut = window.rfind(" ")
        if cut < max_chars // 2:
            cut = max_chars - 1
        else:
            cut += 1
        pieces.append((position, position + cut))
        position += cut
    if position < end:
        pieces.append((position, end))
    return pieces


def split_sections(text: str, max_chars: int = MAX_SECTION_CHARS) -> list[Section]:
    """Split `text` into ordered, contiguous, non-overlapping sections."""
    if max_chars < 2:
        raise ValueError("max_chars must be at least 2")
    if not text:
        return []

    grouped: list[tuple[int, int]] = []
    current: Optional[tuple[int, int]] = None
    for start, end in _paragraph_ranges(text):
        if current is None:
            current = (start, end)
        elif end - current[0] <= max_chars:
            current = (current[0], end)
        else:
            grouped.append(current)
            current = (start, end)
    if current is not None:
        grouped.append(current)

    sections: list[Section] = []
    for start, end in grouped:
        pieces = ((start, end),) if end - start <= max_chars else _split_oversized(
            text, start, end, max_chars,
        )
        for piece_start, piece_end in pieces:
            sections.append(Section(
                index=len(sections),
                text=text[piece_start:piece_end],
                start=piece_start,
                end=piece_end,
            ))
    return sections


def section_count(text: str, max_chars: int = MAX_SECTION_CHARS) -> int:
    """Number of sections the verifier must examine for this text."""
    return len(split_sections(text, max_chars))
