"""Allowlist + extractor tests."""

from allowlist import build_allowlist, domain_ok, host_of
from extractors import extract_fields_rules, is_complete
import extractors


def _sources():
    return [
        {"id": "s1", "provider": "Hugging Face", "canonical_domain": "huggingface.co",
         "account_handle": "@huggingface", "enabled": True, "trust_tier": "A_provider_owned"},
        {"id": "s2", "provider": ".TECH Domains", "canonical_domain": "get.tech",
         "account_handle": None, "enabled": True, "trust_tier": "A_provider_owned"},
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

    def test_disabled_or_untrusted_sources_cannot_authorize(self):
        for override in ({"enabled": False}, {"trust_tier": "B_discovery_lead"},
                         {"trust_tier": "C_excluded"}):
            sources = [{**s, **override} for s in _sources()]
            assert build_allowlist(sources) == {}


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


class TestTypedRuleExtraction:
    """Typed claims are classifications; the server still verifies the quote."""

    def test_free_benefit_is_classified(self):
        fields = extract_fields_rules(
            "Students get a free trial for 30 days.", "https://x.example.com/terms"
        )
        assert fields["benefit_type"]["value"] == "free"

    def test_free_shipping_is_not_a_free_benefit(self):
        fields = extract_fields_rules(
            "Members get free shipping on every order.", "https://x.example.com/terms"
        )
        assert "benefit_type" not in fields

    def test_discount_is_classified(self):
        fields = extract_fields_rules(
            "Use this 40% off discount code.", "https://x.example.com/terms"
        )
        assert fields["benefit_type"]["value"] == "discounted"

    def test_price_inside_a_renewal_clause_is_labelled_renewal(self):
        fields = extract_fields_rules(
            "The first year is free. Afterwards the domain renews at $49.99 per year.",
            "https://x.example.com/terms",
        )
        assert fields["price"]["basis"] == "renewal"

    def test_price_outside_a_renewal_clause_is_labelled_initial(self):
        fields = extract_fields_rules(
            "The first month costs $10 for new accounts.", "https://x.example.com/terms"
        )
        assert fields["price"]["basis"] == "initial"

    def test_worldwide_claim_is_extracted(self):
        fields = extract_fields_rules(
            "This offer is available worldwide for verified students.",
            "https://x.example.com/terms",
        )
        assert fields["regions"]["value"] == "worldwide"

    def test_eligible_regions_are_extracted(self):
        fields = extract_fields_rules(
            "Offer available in the US and PK for students.", "https://x.example.com/terms"
        )
        assert fields["regions"]["value"] == "US, PK"
        assert fields["regions"]["excluded_regions"] == []

    def test_excluded_region_is_recorded(self):
        fields = extract_fields_rules(
            "Offer available in the US and PK, not available in Germany, for students.",
            "https://x.example.com/terms",
        )
        assert fields["regions"]["value"] == "US, PK"
        assert fields["regions"]["excluded_regions"] == ["Germany"]

    def test_auto_renew_yes_and_no(self):
        yes = extract_fields_rules(
            "The plan renews automatically for students.", "https://x.example.com/terms"
        )
        assert yes["auto_renew"]["value"] == "yes"
        no = extract_fields_rules(
            "The plan does not auto-renew automatically for students.",
            "https://x.example.com/terms",
        )
        assert no["auto_renew"]["value"] == "no"


def test_model_reported_conflicts_are_not_discarded(monkeypatch):
    text = "Use code SAVE2026 at checkout for students."
    fields = extract_fields_rules(text, "https://example.com/terms")
    conflict = {"field": "eligibility", "reason": "terms ambiguous"}
    monkeypatch.setattr(extractors, "llm_configured", lambda: True)
    monkeypatch.setattr(extractors, "extract_fields_llm", lambda *args, **kwargs: {
        "fields": fields, "conflicts": [conflict],
    })
    _, conflicts, _ = extractors.extract(text, "https://example.com/terms")
    assert conflict in conflicts
