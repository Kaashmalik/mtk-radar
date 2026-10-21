"""WP01 regression cases: the server, not an extractor, earns verification."""

import asyncio
import copy
import hashlib
import json
import uuid

import pytest
from fastapi import HTTPException

from offers_api import _gate_verified


OFFER_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
EVIDENCE_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
URL = "https://example.com/terms"
TEXT = "Promo code SAVE2026 for verified students only."


def fields():
    return {
        "promo_code": {
            "value": "SAVE2026", "evidence_id": str(EVIDENCE_ID),
            "evidence_url": URL, "excerpt": TEXT, "confidence": 0.8,
        },
        "eligibility": {
            "value": "students", "evidence_id": str(EVIDENCE_ID),
            "evidence_url": URL, "excerpt": TEXT, "confidence": 0.8,
        },
    }


class GatePool:
    """Small query boundary fake; real SQL is exercised by integration tests."""

    def __init__(self, offer_type="coupon"):
        self.offer_type = offer_type
        self.extraction = {
            "fields": json.dumps(fields()), "conflicts": "[]", "complete": True,
            # WP01 slice 8: machine evidence must record what was examined.
            "coverage": json.dumps({
                "version": "paragraph-groups/1", "sections_total": 1,
                "max_section_chars": 6000, "evidence_ids": [str(EVIDENCE_ID)],
            }),
        }
        self.evidence = [{
            "id": EVIDENCE_ID, "url": URL, "official": True, "domain_ok": True,
            "captured_content": TEXT,
            "content_hash": hashlib.sha256(TEXT.encode()).hexdigest(),
            "provider": "Acme", "source_id": None,
            # WP01 slice 3: machine evidence must carry raw bytes + provenance.
            # WP01 slice 6: and a permitted robots.txt decision.
            "reviewer": None, "raw_preserved": True, "requested_url": URL,
            "parser_version": "page_watch/1",
            "robots_url": "https://example.com/robots.txt", "robots_allowed": True,
            "fetch_signature": "a" * 64,
        }]

    async def fetchrow(self, query, *args):
        if "FROM offers" in query:
            return {"offer_type": self.offer_type}
        # The old gate reads these counts and blindly trusts complete=True.
        return {
            "official_ok": 1, "total_evidence": 1, "extraction_complete": True,
            **(self.extraction or {}),
        } if self.extraction is not None else None

    async def fetch(self, query, *args):
        if "FROM sources" in query:
            return [{"canonical_domain": "example.com"}]
        return copy.deepcopy(self.evidence)


def gate(pool):
    return asyncio.run(_gate_verified(pool, OFFER_ID))


def test_valid_bound_quotes_pass():
    gate(GatePool())


@pytest.mark.parametrize("case", [
    "empty_fields", "missing_context", "conflicts", "unrelated_url",
    "foreign_evidence", "invented_quote", "invented_value", "legacy_snapshot",
    "hash_mismatch", "unofficial", "malformed_legacy_fields", "no_extraction",
    "malformed_conflicts", "numeric_substring", "no_raw_provenance",
])
def test_complete_flag_cannot_override_invalid_evidence(case):
    pool = GatePool()
    payload = fields()
    if case == "empty_fields":
        payload = {}
    elif case == "missing_context":
        payload.pop("eligibility")
    elif case == "conflicts":
        pool.extraction["conflicts"] = '[{"field":"eligibility","reason":"disputed"}]'
    elif case == "unrelated_url":
        payload["promo_code"]["evidence_url"] = "https://example.com/unrelated"
    elif case == "foreign_evidence":
        payload["promo_code"]["evidence_id"] = str(uuid.uuid4())
    elif case == "invented_quote":
        payload["promo_code"]["excerpt"] = "Promo code SAVE2026 grants $9999."
    elif case == "invented_value":
        payload["promo_code"]["value"] = "INVENTED9999"
    elif case == "legacy_snapshot":
        pool.evidence[0]["captured_content"] = None
    elif case == "hash_mismatch":
        pool.evidence[0]["content_hash"] = "0" * 64
    elif case == "unofficial":
        pool.evidence = []
    elif case == "malformed_legacy_fields":
        payload = {"promo_code": {"value": True}}
    elif case == "no_extraction":
        pool.extraction = None
    elif case == "malformed_conflicts":
        pool.extraction["conflicts"] = '{}'
    elif case == "numeric_substring":
        payload["promo_code"]["value"] = "SAVE2026"
        payload["promo_code"]["excerpt"] = "Promo code SAVE2026.99 for students."
        pool.evidence[0]["captured_content"] = payload["promo_code"]["excerpt"]
        pool.evidence[0]["content_hash"] = hashlib.sha256(pool.evidence[0]["captured_content"].encode()).hexdigest()
    elif case == "no_raw_provenance":
        pool.evidence[0].update(raw_preserved=False, requested_url=None, parser_version=None)
    if pool.extraction is not None:
        pool.extraction["fields"] = json.dumps(payload)
    with pytest.raises(HTTPException) as exc:
        gate(pool)
    assert exc.value.status_code == 422


def _field(value, excerpt=TEXT, **extra):
    payload = {
        "value": value, "evidence_id": str(EVIDENCE_ID),
        "evidence_url": URL, "excerpt": excerpt,
    }
    payload.update(extra)
    return payload


class TestOfferTypeContract:
    """The offer-type checklist decides completeness, not the caller's flag."""

    def run_gate(self, offer_type, payload, text=TEXT):
        pool = GatePool(offer_type)
        pool.extraction = {
            **pool.extraction,
            "fields": json.dumps(payload), "conflicts": "[]", "complete": True,
        }
        pool.evidence[0]["captured_content"] = text
        pool.evidence[0]["content_hash"] = hashlib.sha256(text.encode()).hexdigest()
        return gate(pool)

    def test_free_trial_without_billing_terms_is_blocked(self):
        """A free trial must prove its ongoing cost, not just a promo code."""
        payload = {
            "promo_code": _field("SAVE2026"),
            "eligibility": _field("students"),
        }
        with pytest.raises(HTTPException) as exc:
            self.run_gate("free_trial", payload)
        assert exc.value.status_code == 422
        assert "renewal" in exc.value.detail
        assert "auto_renew" in exc.value.detail

    def test_free_trial_with_every_required_claim_passes(self):
        text = ("Free trial for students. Use promo code SAVE2026. "
                "Valid until 31 December 2026. "
                "The subscription renews automatically at $19 per month.")
        payload = {
            "value": _field("free trial", text),
            "benefit_type": _field("free", text),
            "eligibility": _field("students", text),
            "expiry": _field("31 December 2026", text),
            "renewal": _field("$19", text),
            "auto_renew": _field("yes", text),
        }
        self.run_gate("free_trial", payload, text)

    def test_negated_eligibility_contradicts_the_claim(self):
        text = "Use promo code SAVE2026. Students are not eligible for this promotion."
        payload = {
            "promo_code": _field("SAVE2026", text),
            "eligibility": _field("students", text),
        }
        with pytest.raises(HTTPException) as exc:
            self.run_gate("coupon", payload, text)
        assert exc.value.status_code == 422
        assert "contradicted" in exc.value.detail

    def test_renewal_price_never_passes_as_the_initial_price(self):
        text = ("New customers only. The first year is free; afterwards the domain "
                "renews at $49.99 per year.")
        payload = {
            "price": _field("$49.99", text, basis="initial"),
            "eligibility": _field("New customers", text),
        }
        with pytest.raises(HTTPException) as exc:
            self.run_gate("domain_discount", payload, text)
        assert exc.value.status_code == 422
        assert "renewal price" in exc.value.detail

    def test_ambiguous_deadline_stays_unknown(self):
        text = "No expiry is stated in the offer terms. Use promo code SAVE2026 for students."
        payload = {
            "promo_code": _field("SAVE2026", text),
            "eligibility": _field("students", text),
            "expiry": _field("no expiry", text),
        }
        with pytest.raises(HTTPException) as exc:
            self.run_gate("credits", payload, text)
        assert exc.value.status_code == 422
        assert "expiry" in exc.value.detail

    def test_unmapped_offer_type_keeps_the_baseline_core(self):
        """An offer type with no published contract still needs incentive + context."""
        payload = {"promo_code": _field("SAVE2026")}
        with pytest.raises(HTTPException) as exc:
            self.run_gate("coupon", payload)
        assert exc.value.status_code == 422
        assert "eligibility" in exc.value.detail


class TestFetchProvenanceGate:
    """WP01 slice 3: machine evidence must prove the bytes it came from."""

    def test_missing_raw_bytes_blocks_promotion(self):
        pool = GatePool()
        pool.evidence[0].update(raw_preserved=False, requested_url=None, parser_version=None)
        with pytest.raises(HTTPException) as exc:
            gate(pool)
        assert exc.value.status_code == 422
        assert "raw page bytes" in exc.value.detail
        assert "robots.txt" in exc.value.detail
        assert "recapture" in exc.value.detail

    def test_reviewer_attested_snapshot_is_exempt(self):
        """A human attestation is recorded in the audit log; no fetch to prove."""
        pool = GatePool()
        pool.evidence[0].update(raw_preserved=False, requested_url=None,
                                parser_version=None, reviewer="Kashi")
        gate(pool)  # must not raise

    def test_missing_robots_permission_blocks_promotion(self):
        """WP01 slice 6: bytes without a permission record are not evidence."""
        pool = GatePool()
        pool.evidence[0].update(robots_url=None, robots_allowed=None)
        with pytest.raises(HTTPException) as exc:
            gate(pool)
        assert exc.value.status_code == 422
        assert "robots.txt" in exc.value.detail

    def test_disallowed_robots_blocks_promotion(self):
        pool = GatePool()
        pool.evidence[0].update(robots_allowed=False)
        with pytest.raises(HTTPException) as exc:
            gate(pool)
        assert "robots.txt" in exc.value.detail

    def test_explicit_opt_out_disables_only_the_provenance_check(self, monkeypatch):
        monkeypatch.setenv("MTK_REQUIRE_FETCH_PROVENANCE", "0")
        pool = GatePool()
        pool.evidence[0].update(raw_preserved=False, requested_url=None, parser_version=None)
        gate(pool)  # must not raise while the deployment opts out

    def test_provenance_requirement_is_on_by_default(self, monkeypatch):
        monkeypatch.delenv("MTK_REQUIRE_FETCH_PROVENANCE", raising=False)
        from offers_api import _require_fetch_provenance
        assert _require_fetch_provenance() is True

    def test_missing_signature_blocks_promotion(self):
        """WP01 slice 7: bytes and permission without an attested author."""
        pool = GatePool()
        pool.evidence[0].update(fetch_signature=None)
        with pytest.raises(HTTPException) as exc:
            gate(pool)
        assert exc.value.status_code == 422
        assert "signed acquisition record" in exc.value.detail

    def test_signature_requirement_is_on_by_default(self, monkeypatch):
        monkeypatch.delenv("MTK_REQUIRE_FETCH_SIGNATURE", raising=False)
        from offers_api import _require_fetch_signature
        assert _require_fetch_signature() is True

    def test_signature_opt_out_allows_legacy_rows(self, monkeypatch):
        monkeypatch.setenv("MTK_REQUIRE_FETCH_SIGNATURE", "0")
        pool = GatePool()
        pool.evidence[0].update(fetch_signature=None)
        gate(pool)  # must not raise while the deployment opts out


class TestExtractionCoverageGate:
    """WP01 slice 8: no record of what was examined, no verification."""

    def test_missing_coverage_blocks_promotion(self):
        pool = GatePool()
        pool.extraction["coverage"] = None
        with pytest.raises(HTTPException) as exc:
            gate(pool)
        assert exc.value.status_code == 422
        assert "coverage record" in exc.value.detail

    def test_coverage_must_list_the_snapshots_the_claims_use(self):
        pool = GatePool()
        pool.extraction["coverage"] = json.dumps({
            "version": "paragraph-groups/1", "sections_total": 1,
            "max_section_chars": 6000, "evidence_ids": [str(uuid.uuid4())],
        })
        with pytest.raises(HTTPException) as exc:
            gate(pool)
        assert exc.value.status_code == 422
        assert "does not include" in exc.value.detail

    def test_reviewer_attested_extraction_is_exempt(self):
        pool = GatePool()
        pool.extraction["coverage"] = None
        pool.evidence[0]["reviewer"] = "Kashi"
        gate(pool)  # must not raise: a human attested the snapshot

    def test_coverage_requirement_is_on_by_default(self, monkeypatch):
        monkeypatch.delenv("MTK_REQUIRE_EXTRACTION_COVERAGE", raising=False)
        from offers_api import _require_extraction_coverage
        assert _require_extraction_coverage() is True

    def test_coverage_opt_out_allows_legacy_rows(self, monkeypatch):
        monkeypatch.setenv("MTK_REQUIRE_EXTRACTION_COVERAGE", "0")
        pool = GatePool()
        pool.extraction["coverage"] = None
        gate(pool)
