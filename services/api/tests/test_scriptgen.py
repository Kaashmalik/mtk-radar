"""Script generator tests — gate, citations, command-card safety."""

import pytest

from scriptgen import (
    ScriptGateError,
    assert_video_allowed,
    build_checklist,
    build_command_cards,
    generate,
    render_script_md,
)

OFFER = {
    "id": "o1",
    "title": "One-year .tech domain promotion",
    "provider": ".TECH Domains",
    "state": "verified",
    "eligibility": {"countries": ["US", "PK"], "studentStatus": True, "verificationRequired": True},
    "claim_steps": [
        {"order": 1, "kind": "account_action", "text": "Sign in to the student benefit portal",
         "url": "https://examples.example.edu/benefits"},
        {"order": 2, "kind": "command", "text": "nslookup myproject.tech 1.1.1.1",
         "source_url": "https://docs.example.com/dns-verify", "expected_output": "status: NOERROR",
         "shell_os": "Windows PowerShell 5.1"},
    ],
    "promo_code": "STUDENT24",
    "redemption_url": "https://get.tech/students",
    "expires_at": "2027-01-31T00:00:00Z",
    "renewal": {"autoRenew": True, "regularPrice": "$49.99/yr"},
}

EVIDENCE = [
    {"url": "https://get.tech/students", "captured_at": "2026-10-21T10:00:00Z", "excerpt": "1-year free"},
    {"url": "https://education.github.com/pack", "captured_at": "2026-10-21T10:01:00Z", "excerpt": "includes .TECH"},
]


class TestGate:
    @pytest.mark.parametrize("state", ["candidate", "evidence_needed", "expired", "corrected"])
    def test_unverified_blocked(self, state):
        with pytest.raises(ScriptGateError):
            assert_video_allowed(state)

    @pytest.mark.parametrize("state", ["verified", "approved_for_video", "published"])
    def test_verified_allowed(self, state):
        assert_video_allowed(state)  # must not raise

    def test_generate_blocked_for_unverified(self):
        with pytest.raises(ScriptGateError):
            generate({**OFFER, "state": "evidence_needed"}, EVIDENCE)


class TestGeneratedScript:
    def setup_method(self):
        self.result = generate(OFFER, EVIDENCE)
        self.md = self.result["markdown"]

    def test_checked_on_date_present(self):
        assert "Checked on" in self.md

    def test_eligibility_up_front(self):
        assert "students" in self.md and "PK" in self.md

    def test_expiry_surfaced(self):
        assert "31" in self.md and "2027" in self.md

    def test_renewal_warning_present(self):
        assert "$49.99" in self.md and "renew" in self.md.lower()

    def test_evidence_urls_cited(self):
        for ev in EVIDENCE:
            assert ev["url"] in self.md

    def test_checklist_has_redaction_step(self):
        texts = " ".join(s["text"] for s in self.result["checklist"])
        assert "Redaction" in texts

    def test_command_card_safety(self):
        card = self.result["command_cards"][0]
        assert card["command"].startswith("nslookup")
        assert card["source_url"] == "https://docs.example.com/dns-verify"
        assert card["unsafe_reasons"] == []


class TestUnknownWording:
    """An unknown fact never becomes a selling point (master plan §6 step 7, A13)."""

    def _unknown_offer(self, **facts):
        return {
            "id": "o2", "title": "Free trial", "provider": "Acme", "state": "verified",
            "eligibility": {}, "value": {}, "claim_steps": [],
            "promo_code": None, "redemption_url": None, "expires_at": None,
            "renewal": {}, "category": "ai_tools", "offer_type": "free_trial",
            "fact_pack": facts,
        }

    def test_unknown_eligibility_is_not_open_eligibility(self):
        markdown = generate(self._unknown_offer(
            eligibility={"status": "unknown"},
        ), EVIDENCE)["markdown"]
        assert "Open eligibility" not in markdown
        assert "Eligibility is not stated in the inspected terms" in markdown
        assert "Do not present this offer as open to everyone" in markdown

    def test_contradicted_eligibility_requires_review(self):
        markdown = generate(self._unknown_offer(
            eligibility={"status": "contradicted"},
        ), EVIDENCE)["markdown"]
        assert "contradict" in markdown.lower()
        assert "manual review is required" in markdown

    def test_absent_expiry_is_not_never_expires(self):
        markdown = generate(self._unknown_offer(
            expiry={"status": "unknown"},
        ), EVIDENCE)["markdown"]
        assert "no expiry stated in the inspected terms" in markdown
        assert "not proof the offer never expires" in markdown

    def test_unknown_renewal_is_not_free(self):
        markdown = generate(self._unknown_offer(
            renewal={"status": "unknown"},
        ), EVIDENCE)["markdown"]
        assert "Unknown renewal is not free" in markdown
        # "none stated" reads as "no charge" and must not appear.
        assert "none stated" not in markdown

    def test_contradicted_renewal_requires_review(self):
        markdown = generate(self._unknown_offer(
            renewal={"status": "contradicted"},
        ), EVIDENCE)["markdown"]
        assert "contradict" in markdown.lower()
        assert "manual review is required" in markdown


class TestCommandCardSafety:
    def test_missing_source_flagged(self):
        cards = build_command_cards([{"kind": "command", "text": "rm -rf /"}])
        assert any("official source" in r for r in cards[0]["unsafe_reasons"])

    def test_missing_expected_output_flagged(self):
        cards = build_command_cards([{"kind": "command", "text": "ls", "source_url": "https://docs.example.com"}])
        assert any("expected output" in r for r in cards[0]["unsafe_reasons"])

    def test_destructive_and_billable_flagged(self):
        cards = build_command_cards([
            {"kind": "command", "text": "aws ec2 run-instances", "source_url": "https://docs.aws.amazon.com/cli/latest/reference/ec2/run-instances.html",
             "expected_output": "instance id", "destructive": True, "billable": True},
        ])
        reasons = " ".join(cards[0]["unsafe_reasons"])
        assert "DESTRUCTIVE" in reasons and "BILLABLE" in reasons

    def test_non_command_steps_ignored(self):
        assert build_command_cards([{"kind": "manual_check", "text": "sign in"}]) == []


class TestChecklist:
    def test_claim_steps_appended_in_order(self):
        checklist = build_checklist(OFFER)
        texts = [s["text"] for s in checklist]
        assert any("Sign in to the student benefit portal" in t for t in texts)
        orders = [s["order"] for s in checklist]
        assert orders == sorted(orders)

    def test_country_check_from_eligibility(self):
        texts = " ".join(s["text"] for s in build_checklist(OFFER))
        assert "US, PK" in texts

    def test_render_uses_same_checklist(self):
        checklist = build_checklist(OFFER)
        md = render_script_md(OFFER, checklist, [], EVIDENCE)
        assert "Claim steps" in md
