"""Allowlist + extractor tests."""

from allowlist import build_allowlist, domain_ok, host_of
from extractors import extract_fields_rules, is_complete


def _sources():
    return [
        {"id": "s1", "provider": "Hugging Face", "canonical_domain": "huggingface.co",
         "account_handle": "@huggingface"},
        {"id": "s2", "provider": ".TECH Domains", "canonical_domain": "get.tech",
         "account_handle": None},
    ]


class TestAllowlist:
    def test_exact_domain_allowed(self):
        allow = build_allowlist(_sources())
        assert domain_ok(allow, "Hugging Face", "https://huggingface.co/docs/pricing")

    def test_subdomain_allowed(self):
        allow = build_allowlist(_sources())
        assert domain_ok(allow, "hugging face", "https://cdn.huggingface.co/x")

    def test_unregistered_provider_denied(self):
        allow = build_allowlist(_sources())
        assert not domain_ok(allow, "Unknown LLC", "https://unknown.example.com/deal")

    def test_lookalike_domain_denied(self):
        allow = build_allowlist(_sources())
        assert not domain_ok(allow, "Hugging Face", "https://huggingface.co.evil.io/free")
        assert not domain_ok(allow, "Hugging Face", "https://not-huggingface.co/free")

    def test_wrong_registered_domain_denied(self):
        allow = build_allowlist(_sources())
        assert not domain_ok(allow, "Hugging Face", "https://get.tech/promo")

    def test_host_of_strips(self):
        assert host_of("https://WWW.Example.com/a") == "www.example.com"


class TestRuleExtractor:
    def test_extracts_promo_and_price_and_expiry(self):
        text = (
            "One-year .TECH domain free for students. Use code STUDENT24 at checkout. "
            "Regular price $49.99 after the first year. Offer ends January 31, 2027. "
            "Only for new customers with verified enrollment."
        )
        fields = extract_fields_rules(text, "https://get.tech/students")
        assert fields["promo_code"]["value"] == "STUDENT24"
        assert "$" in fields["price"]["value"]
        assert fields["expiry"]["value"] == "January 31, 2027"
        assert fields["eligibility"]["value"].lower().startswith("student")

    def test_every_field_links_to_evidence(self):
        text = "Free for students, code STUDENT24 at checkout, $49.99 afterwards."
        fields = extract_fields_rules(text, "https://get.tech/terms")
        for field in fields.values():
            assert field["evidence_url"] == "https://get.tech/terms"
            assert field["excerpt"]
            assert 0 < field["confidence"] <= 1

    def test_empty_text_no_fields(self):
        assert extract_fields_rules("", "https://x.example.com") == {}
        assert not is_complete({})

    def test_incomplete_without_eligibility_or_expiry(self):
        fields = extract_fields_rules("Promo code SAVE10 at checkout.", "https://x.example.com")
        assert "promo_code" in fields
        assert not is_complete(fields)

    def test_complete_with_incentive_and_context(self):
        text = (
            "Verified students get one year free, promo code STUDENT24 at checkout. "
            "Price afterwards $49.99. Offer ends January 31, 2027."
        )
        fields = extract_fields_rules(text, "https://get.tech/terms")
        assert is_complete(fields)
