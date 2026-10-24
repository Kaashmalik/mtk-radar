"""G18 (EP-03) — research-track script generation.

The claim ledger is the content contract:
- a CONTRADICTED claim blocks generation in every track,
- an explainer renders per-class attribution ("the authors report" is
  sourcing, our interpretation is labeled analysis) and never invents
  coupon/price fields around a paper,
- the 'offer' track keeps the legacy wording untouched (regression guard),
- the format a track may borrow is fail-closed.
"""

import pytest

from scriptgen import (
    CONTENT_TYPES,
    ScriptGateError,
    assert_content_type_format,
    assert_research_cleared,
    content_type_of,
    generate,
    research_attribution_lines,
)

OFFER = {
    "id": "o1",
    "title": "Does the two-week memory protocol work?",
    "provider": "Sleep & Cognition Lab",
    "state": "verified",
    "eligibility": {},
    "claim_steps": [],
    # A stray field from an old template run: a research track must NEVER
    # render it as a coupon.
    "promo_code": "SAVE10",
    "redemption_url": "https://lab.example.edu/paper",
    "renewal": {},
}

BRIEF_CLAIMS = [
    {
        "claim_text": "Participants recalled 12% more words after two weeks.",
        "claim_class": "author_reported",
        "status": "supported",
        "source_owner": "Sleep & Cognition Lab (2025)",
        "permitted_wording": None,
    },
    {
        "claim_text": "Two independent labs reproduced the 12% recall gain.",
        "claim_class": "independently_reproduced",
        "status": "supported",
        "source_url": "https://replication.example.edu/study",
    },
    {
        "claim_text": "The protocol helps shift workers most.",
        "claim_class": "editorial_analysis",
        "status": "unknown",
    },
    {
        "claim_text": "Marker protein dropped 30% in the treated group.",
        "claim_class": "author_reported",
        "status": "contradicted",
    },
]


def _offer(content_type: str = "explainer", claims: list | None = None) -> dict:
    return {
        **OFFER,
        "content_type": content_type,
        "research": {"content_type": content_type, "claims": claims or []},
    }


class TestContradictionGate:
    def test_contradicted_claim_blocks_generation(self):
        offer = _offer(claims=[
            {"claim_text": "Marker protein dropped 30%.",
             "claim_class": "author_reported", "status": "contradicted"}])
        with pytest.raises(ScriptGateError, match="contradicted"):
            generate(offer, [], language="en")

    def test_contradicted_claim_blocks_offer_track_too(self):
        offer = _offer(content_type="offer", claims=[
            {"claim_text": "The renewal is free forever.",
             "claim_class": "editorial_analysis", "status": "contradicted"}])
        with pytest.raises(ScriptGateError):
            generate(offer, [], language="en")

    def test_human_resolution_clears_the_block(self):
        # After the reviewer flips the claim to 'supported' the gate unblocks.
        offer = _offer(claims=[
            {"claim_text": "Marker protein dropped 30%.",
             "claim_class": "author_reported", "status": "supported"}])
        assert assert_research_cleared(offer) == []

    def test_all_four_classes_render_attributed(self):
        offer = _offer(claims=[
            {**BRIEF_CLAIMS[0]}, {**BRIEF_CLAIMS[1]}, {**BRIEF_CLAIMS[2]}])
        payload = generate(offer, [], language="en")
        markdown = payload["markdown"]
        assert "The authors report" in markdown
        assert "Independently reproduced by other researchers" in markdown
        assert "Our analysis" in markdown
        # 'labeled analysis' branch of the acceptance: an UNKNOWN claim never
        # passes as confirmed.
        assert "not yet independently confirmed" in markdown
        # permitted wording is quoted verbatim when the ledger recorded it
        strict = _offer(claims=[{**BRIEF_CLAIMS[0],
                                 "permitted_wording": "Word recall improved."}])
        markdown = generate(strict, [], language="en")["markdown"]
        assert "Word recall improved." in markdown


class TestResearchTrackSourcing:
    def test_explainer_never_renders_coupon(self):
        # The stray promo_code must not leak into a research explainer.
        payload = generate(_offer("explainer", claims=[
            {**BRIEF_CLAIMS[0]}]), [], language="en")
        assert "SAVE10" not in payload["markdown"]
        assert "Promo code" not in payload["markdown"]

    def test_explainer_marks_payload_content_type(self):
        payload = generate(_offer("explainer"), [], language="en")
        assert payload["content_type"] == "explainer"
        assert payload["format"] == "official_explainer"

    def test_explainer_track_cannot_borrow_first_person_formats(self):
        with pytest.raises(ScriptGateError, match="does not allow"):
            generate(_offer("explainer"), [], language="en",
                     script_format="tested_tutorial")
        with pytest.raises(ScriptGateError, match="does not allow"):
            generate(_offer("explainer"), [], language="en",
                     script_format="claim_walkthrough")

    def test_tutorial_track_keeps_capture_gates(self):
        # tested_tutorial track still requires the human-reviewed capture for
        # the first-person format (capture checks are NOT removed by tracks).
        with pytest.raises(ScriptGateError, match="redaction"):
            generate(_offer("tested_tutorial"), [], language="en",
                     script_format="tested_tutorial")

    def test_offer_track_renders_promo_unchanged(self):
        offer = _offer("offer", claims=[
            {**BRIEF_CLAIMS[0], "status": "supported"}])
        offer["renewal"] = {"autoRenew": True, "regularPrice": "$49.99/yr"}
        payload = generate(offer, [], language="en")
        assert "Promo code: `SAVE10`" in payload["markdown"]


class TestContentTypeId:
    def test_defaults_to_offer_track(self):
        assert content_type_of({"state": "verified"}) == "offer"

    def test_brief_supplies_content_type_when_row_missing(self):
        offer = {"state": "verified",
                 "research": {"content_type": "explainer", "claims": []}}
        assert content_type_of(offer) == "explainer"

    def test_unknown_content_type_fails_closed(self):
        with pytest.raises(ScriptGateError, match="unknown content type"):
            assert_content_type_format("paper_dump", "official_explainer")

    def test_registry_shapes(self):
        assert set(CONTENT_TYPES) == {
            "explainer", "tested_tutorial", "claim_walkthrough", "offer"}


class TestAttributionUrdu:
    def test_urdu_framing_and_unconfirmed_label(self):
        offer = _offer("explainer", claims=[{**BRIEF_CLAIMS[0]},
                                            {**BRIEF_CLAIMS[2]}])
        lines = research_attribution_lines(offer, language="ur")
        assert lines
        assert any("محققین کا کہنا ہے" in ln for ln in lines)
        assert any("ابھی آزادانہ تصدیق نہیں ہوئی" in ln for ln in lines)
