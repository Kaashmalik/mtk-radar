"""Storyboard honesty rules (V7) — shared by the API editor and renderer."""

import pytest

import storyboard as sb

BRIEF = {
    "id": "b1", "version": 3, "viewer_question": "Does it work?", "angle": "What it shows",
    "limitations": "Small sample.",
    "claims": [
        {"id": "c1", "claim_text": "Recall rose 12%.", "claim_class": "author_reported",
         "status": "supported", "source_owner": "arXiv", "source_date": "2026-10-20"},
        {"id": "c2", "claim_text": "Effect lasts a week.", "claim_class": "author_reported",
         "status": "unknown"},
        {"id": "c3", "claim_text": "Replaces sleep.", "claim_class": "editorial_analysis",
         "status": "contradicted"},
    ],
}
PAGES = [{"id": "p1", "url": "https://arxiv.org/abs/1", "final_url": "https://arxiv.org/abs/1",
          "title": "The paper", "status": "ok", "captured_at": "2026-10-28T10:00:00+00:00"},
         {"id": "p2", "url": "https://x.org", "status": "failed"}]


def test_suggestion_orders_title_pages_claims_close_and_skips_contradictions():
    scenes = sb.suggest({"title": "T"}, BRIEF, PAGES)
    assert [s["kind"] for s in scenes] == ["title", "page", "claim", "claim", "close"]
    assert all(s["include"] and s["weight"] == 1.0 for s in scenes)
    assert "Replaces sleep." not in [s.get("body") for s in scenes]
    assert scenes[1]["source"] == "Source: arxiv.org · captured 2026-10-28"


def test_claim_wording_and_attribution_cannot_be_rewritten_in_the_editor():
    edits = [{"kind": "claim", "claim_ids": ["c2"], "heading": "Proven fact",
              "body": "It works forever!", "weight": 2}]
    scenes, problems = sb.validate(edits, BRIEF, PAGES)
    assert problems == []
    assert scenes[0]["body"] == "Effect lasts a week."
    assert scenes[0]["heading"].endswith("not yet independently confirmed")
    assert scenes[0]["weight"] == 2


@pytest.mark.parametrize("edit,problem", [
    ({"kind": "claim", "claim_ids": ["c3"]}, "contradicted"),
    ({"kind": "claim", "claim_ids": ["nope"]}, "not in the current research brief"),
    ({"kind": "page", "page_capture_id": "p2"}, "page capture missing or failed"),
    ({"kind": "title", "heading": "   "}, "needs a heading"),
    ({"kind": "video"}, "unknown kind"),
])
def test_invalid_scenes_are_refused_with_reasons(edit, problem):
    _, problems = sb.validate([{"kind": "close", "heading": "End"}, edit], BRIEF, PAGES)
    assert any(problem in p for p in problems), problems


def test_free_text_is_bounded_and_control_free_and_weights_clamped():
    edits = [{"kind": "title", "heading": "Q" + chr(0) + "uestion" + "x" * 500,
              "body": "a" + chr(9) + "b", "weight": 99},
             {"kind": "page", "page_capture_id": "p1", "body": "caption", "weight": 0}]
    scenes, problems = sb.validate(edits, BRIEF, PAGES)
    assert not problems
    assert chr(0) not in scenes[0]["heading"]
    assert len(scenes[0]["heading"]) == sb.MAX_HEADING
    assert scenes[0]["weight"] == sb.MAX_WEIGHT and scenes[1]["weight"] == sb.MIN_WEIGHT
    assert scenes[1]["source"].startswith("Source: arxiv.org"), "page source is derived"


def test_duplicates_empty_and_all_excluded_are_refused():
    _, problems = sb.validate([{"kind": "title", "heading": "A"},
                               {"kind": "title", "heading": "B"}], BRIEF, PAGES)
    assert any("duplicate" in p for p in problems)
    _, problems = sb.validate([], BRIEF, PAGES)
    assert problems
    _, problems = sb.validate([{"kind": "title", "heading": "A", "include": False}],
                              BRIEF, PAGES)
    assert any("at least one scene" in p for p in problems)


def test_timing_uses_weights_and_skips_excluded_scenes():
    scenes = [{"id": "a", "kind": "title", "weight": 1, "include": True},
              {"id": "b", "kind": "close", "weight": 3, "include": True},
              {"id": "c", "kind": "close", "weight": 1, "include": False}]
    timed = sb.apply_timing(scenes, total_s=40)
    assert [s["id"] for s in timed] == ["a", "b"]
    assert timed[0]["end"] == pytest.approx(10) and timed[1]["end"] == pytest.approx(40)
    assert sb.digest(timed) == sb.digest(sb.apply_timing(scenes, total_s=40))
