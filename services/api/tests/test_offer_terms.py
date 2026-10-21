"""Offer-type terms contract tests (master plan §6 steps 5-9).

These are pure unit tests of the fact-pack logic: no database, no network.
The point of every case is that a literal quote alone must never be mistaken
for a claimable, universal or free offer.
"""

import pytest

from offer_terms import (
    CONTRADICTED,
    NOT_APPLICABLE,
    SUPPORTED,
    UNKNOWN,
    build_fact_pack,
    classify_field,
    derive_completeness,
    fact_pack_problems,
    required_fields,
)


def field(value, excerpt, **extra):
    payload = {"value": value, "excerpt": excerpt}
    payload.update(extra)
    return payload


class TestStatusVocabulary:
    def test_exactly_four_statuses(self):
        assert {SUPPORTED, CONTRADICTED, UNKNOWN, NOT_APPLICABLE} == {
            "supported", "contradicted", "unknown", "not_applicable",
        }

    def test_fact_pack_covers_every_claim_field(self):
        pack = build_fact_pack("coupon", {})
        assert set(pack) == {
            "promo_code", "price", "value", "benefit_type", "eligibility",
            "regions", "expiry", "renewal", "auto_renew",
        }

    def test_unrequired_absent_field_is_not_applicable(self):
        pack = build_fact_pack("coupon", {})
        assert pack["renewal"]["status"] == NOT_APPLICABLE

    def test_required_absent_field_is_unknown_not_absent(self):
        pack = build_fact_pack("free_trial", {})
        assert pack["renewal"]["status"] == UNKNOWN
        assert pack["auto_renew"]["status"] == UNKNOWN


class TestNegation:
    """A page can contain the value and still state the opposite."""

    def test_negated_eligibility_is_contradicted(self):
        result = classify_field("eligibility", field(
            "students", "Use promo code SAVE2026. Students are not eligible for this offer."
        ))
        assert result["status"] == CONTRADICTED

    def test_negated_free_claim_is_contradicted(self):
        result = classify_field("benefit_type", field(
            "free", "This plan is not free for existing accounts."
        ))
        assert result["status"] == CONTRADICTED

    def test_negation_elsewhere_in_the_quote_does_not_contradict(self):
        """A contradicting phrase must sit next to the claimed value."""
        result = classify_field("price", field(
            "$10", "Shipping is not free. The plan costs $10 per month."
        ))
        assert result["status"] == SUPPORTED

    def test_expired_offer_contradicts_the_deadline(self):
        result = classify_field("expiry", field(
            "31 December 2026", "This promotion has expired. It ended 31 December 2026."
        ))
        assert result["status"] == CONTRADICTED


class TestAmbiguity:
    """An unstated fact stays unknown; it never becomes a claim."""

    @pytest.mark.parametrize("value,quote", [
        ("no expiry", "These terms state no expiry for the promotion."),
        ("never expires", "The page claims the offer never expires."),
        ("ongoing", "The promotion is described as ongoing in the terms."),
        ("TBD", "The end date is listed as TBD in the terms."),
        ("end of year", "The promotion runs until end of year."),
    ])
    def test_non_specific_deadline_is_unknown(self, value, quote):
        result = classify_field("expiry", field(value, quote))
        assert result["status"] == UNKNOWN
        assert "never expires" in result["reason"]

    def test_specific_deadline_is_supported(self):
        result = classify_field("expiry", field(
            "31 December 2026", "The offer ends on 31 December 2026."
        ))
        assert result["status"] == SUPPORTED

    def test_iso_deadline_is_supported(self):
        result = classify_field("expiry", field(
            "2026-12-31", "The offer ends 2026-12-31."
        ))
        assert result["status"] == SUPPORTED

    def test_renewal_claim_without_a_renewal_clause_is_unknown(self):
        result = classify_field("renewal", field(
            "$49.99", "The plan costs $49.99 per year."
        ))
        assert result["status"] == UNKNOWN

    def test_auto_renew_claim_without_support_is_unknown(self):
        result = classify_field("auto_renew", field(
            "yes", "The subscription renews each year at the standard rate."
        ))
        assert result["status"] == UNKNOWN

    def test_auto_renew_yes_is_supported_by_an_explicit_clause(self):
        result = classify_field("auto_renew", field(
            "yes", "The subscription renews automatically unless cancelled."
        ))
        assert result["status"] == SUPPORTED

    def test_free_needs_a_free_benefit_not_free_shipping(self):
        result = classify_field("benefit_type", field(
            "free", "Members get free shipping on every order."
        ))
        assert result["status"] == UNKNOWN
        assert "free benefit" in result["reason"]

    def test_free_benefit_is_supported(self):
        result = classify_field("benefit_type", field(
            "free", "Students get a free trial for 30 days."
        ))
        assert result["status"] == SUPPORTED

    def test_application_based_needs_application_language(self):
        result = classify_field("benefit_type", field(
            "application_based", "Students receive a reduced rate."
        ))
        assert result["status"] == UNKNOWN

    def test_application_based_is_supported_by_application_language(self):
        result = classify_field("benefit_type", field(
            "application_based", "Students must apply for the scholarship award."
        ))
        assert result["status"] == SUPPORTED


class TestPriceBasis:
    """A renewal price must never be presented as the initial price."""

    def test_unstated_basis_inside_a_renewal_clause_is_unknown(self):
        result = classify_field("price", field(
            "$49.99", "The first year is free; afterwards the domain renews at $49.99."
        ))
        assert result["status"] == UNKNOWN
        assert "basis" in result["reason"]

    def test_initial_basis_contradicted_by_a_renewal_clause(self):
        result = classify_field("price", field(
            "$49.99", "The first year is free; afterwards the domain renews at $49.99.",
            basis="initial",
        ))
        assert result["status"] == CONTRADICTED
        assert "renewal price" in result["reason"]

    def test_initial_basis_outside_a_renewal_clause_is_supported(self):
        result = classify_field("price", field(
            "$10", "The first month costs $10.", basis="initial",
        ))
        assert result["status"] == SUPPORTED
        assert result["basis"] == "initial"

    def test_renewal_basis_is_supported(self):
        result = classify_field("price", field(
            "$49.99", "Afterwards the domain renews at $49.99 per year.", basis="renewal",
        ))
        assert result["status"] == SUPPORTED
        assert result["basis"] == "renewal"


class TestRegions:
    def test_worldwide_claim_contradicted_by_an_exclusion(self):
        result = classify_field("regions", field(
            "worldwide", "Available worldwide, except in Germany."
        ))
        assert result["status"] == CONTRADICTED

    def test_worldwide_claim_with_recorded_exclusions_is_contradicted(self):
        result = classify_field("regions", field(
            "worldwide", "Available worldwide.", excluded_regions=["Germany"],
        ))
        assert result["status"] == CONTRADICTED

    def test_exclusion_without_a_recorded_region_is_unknown(self):
        result = classify_field("regions", field(
            "US, PK", "Offer available in the US and PK, not available in Germany."
        ))
        assert result["status"] == UNKNOWN

    def test_specific_regions_are_supported(self):
        result = classify_field("regions", field(
            "US, PK", "Offer available in the US and PK."
        ))
        assert result["status"] == SUPPORTED


class TestOfferTypeChecklist:
    def test_free_trial_requires_billing_terms(self):
        assert set(required_fields("free_trial")) == {
            "value", "benefit_type", "eligibility", "expiry", "renewal", "auto_renew",
        }

    def test_unmapped_offer_type_has_no_contract(self):
        assert required_fields("some_unheard_of_type") == ()

    def test_missing_required_field_blocks_completion(self):
        pack = build_fact_pack("free_trial", {
            "value": field("free trial", "Free trial for students."),
        })
        complete, problems = derive_completeness("free_trial", pack)
        assert complete is False
        assert any("renewal" in problem for problem in problems)

    def test_every_required_field_supported_passes(self):
        text = ("Free trial for students. Valid until 31 December 2026. "
                "The subscription renews automatically at $19 per month.")
        pack = build_fact_pack("free_trial", {
            "value": field("free trial", text),
            "benefit_type": field("free", text),
            "eligibility": field("students", text),
            "expiry": field("31 December 2026", text),
            "renewal": field("$19", text),
            "auto_renew": field("yes", text),
        })
        complete, problems = derive_completeness("free_trial", pack)
        assert problems == []
        assert complete is True

    def test_unestablished_field_is_unknown_even_when_quoted(self):
        """A quote that was not proven against the snapshot is not support."""
        pack = build_fact_pack("coupon", {
            "promo_code": field("SAVE2026", "Use promo code SAVE2026."),
            "eligibility": field("students", "Use promo code SAVE2026."),
        }, established={"promo_code"})
        assert pack["eligibility"]["status"] == UNKNOWN
        complete, problems = derive_completeness("coupon", pack)
        assert complete is False

    def test_unmapped_type_keeps_the_baseline_core(self):
        pack = build_fact_pack("coupon", {
            "promo_code": field("SAVE2026", "Use promo code SAVE2026."),
        })
        complete, problems = derive_completeness("coupon", pack)
        assert complete is False
        assert any("eligibility" in problem for problem in problems)

    def test_unmapped_type_with_incentive_and_context_passes(self):
        pack = build_fact_pack("coupon", {
            "promo_code": field("SAVE2026", "Use promo code SAVE2026 for students."),
            "eligibility": field("students", "Use promo code SAVE2026 for students."),
        })
        complete, problems = derive_completeness("coupon", pack)
        assert problems == []
        assert complete is True

    def test_contradiction_is_always_reported_even_for_optional_fields(self):
        pack = build_fact_pack("coupon", {
            "promo_code": field("SAVE2026", "Use promo code SAVE2026 for students."),
            "eligibility": field("students", "Use promo code SAVE2026 for students."),
            "auto_renew": field("yes",
                                "Use promo code SAVE2026 for students. "
                                "The plan does not auto-renew."),
        })
        problems = fact_pack_problems("coupon", pack)
        assert any("auto_renew: contradicted" in problem for problem in problems)


class TestFactPackIsDerived:
    def test_pack_records_the_reason_for_each_status(self):
        pack = build_fact_pack("coupon", {})
        assert all("reason" in entry for entry in pack.values())
        assert all("status" in entry for entry in pack.values())

    def test_required_flag_marks_contract_fields(self):
        pack = build_fact_pack("free_trial", {})
        assert pack["renewal"]["required"] is True
        assert pack["regions"]["required"] is False
