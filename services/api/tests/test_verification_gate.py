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

    def __init__(self):
        self.extraction = {"fields": json.dumps(fields()), "conflicts": "[]", "complete": True}
        self.evidence = [{
            "id": EVIDENCE_ID, "url": URL, "official": True, "domain_ok": True,
            "captured_content": TEXT,
            "content_hash": hashlib.sha256(TEXT.encode()).hexdigest(),
            "provider": "Acme", "source_id": None,
        }]

    async def fetchrow(self, query, *args):
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
    "malformed_conflicts", "numeric_substring",
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
    if pool.extraction is not None:
        pool.extraction["fields"] = json.dumps(payload)
    with pytest.raises(HTTPException) as exc:
        gate(pool)
    assert exc.value.status_code == 422
