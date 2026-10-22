"""Bilingual script generation — same facts, separate approval hashes."""

import pytest

from scriptgen import ScriptGateError, generate, generate_multilingual


OFFER = {
    "title": "One-year .tech domain",
    "provider": "Example Registrar",
    "state": "verified",
    "redemption_url": "https://example.com/student",
    "promo_code": "STUDENT24",
    "eligibility": {"countries": ["PK"], "studentStatus": True,
                    "verificationRequired": True},
    "renewal": {"regularPrice": "$12/year", "autoRenew": True},
    "expires_at": "2027-01-31T00:00:00+00:00",
    "claim_steps": [
        {"kind": "manual_check", "text": "Open the official benefit page."},
        {"kind": "command", "text": "example --verify",
         "source_url": "https://example.com/docs", "expected_output": "verified"},
    ],
}
EVIDENCE = [{"url": "https://example.com/terms", "captured_at": "2026-10-20T00:00:00Z"}]


def test_multilingual_builds_both_languages_from_the_same_facts():
    result = generate_multilingual(OFFER, EVIDENCE)
    assert set(result["languages"]) == {"en", "ur"}
    english = result["languages"]["en"]["markdown"]
    urdu = result["languages"]["ur"]["markdown"]
    assert "official terms explainer" in english
    assert "i claimed" not in english.lower()
    assert "آفیشل شرائط کی وضاحت" in urdu
    assert "میں نے" not in urdu
    assert english != urdu
    assert "https://example.com/terms" in english
    assert "https://example.com/terms" in urdu


def test_language_versions_have_distinct_hashes():
    from schedules_state import script_version_hash

    en = generate(OFFER, EVIDENCE, language="en")
    ur = generate(OFFER, EVIDENCE, language="ur")
    assert script_version_hash(en["markdown"]) != script_version_hash(ur["markdown"])


def test_urdu_script_keeps_renewal_and_eligibility_warnings():
    markdown = generate(OFFER, EVIDENCE, language="ur")["markdown"]
    assert "خودکار تجدید" in markdown
    assert "صرف طلبہ" in markdown
    assert "$12/year" in markdown


def test_unverified_offer_still_cannot_generate_any_language():
    with pytest.raises(ScriptGateError):
        generate({**OFFER, "state": "evidence_needed"}, EVIDENCE, language="ur")
    with pytest.raises(ScriptGateError):
        generate({**OFFER, "state": "evidence_needed"}, EVIDENCE, language="en")


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError):
        generate(OFFER, EVIDENCE, language="fr")
