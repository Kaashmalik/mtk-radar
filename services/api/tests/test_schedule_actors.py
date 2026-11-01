"""Machine-credential actor attribution on schedules (review P1-1).

Sharpest case the fix closes: a worker/service token creating a TikTok
schedule recorded `consent_by: "reviewer"` (the route's human-sounding
default). Now the recorded actor is the credential's MACHINE identity, and
TikTok consent — a human attestation — is refused outright for any machine
actor before a single database statement runs.
"""

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schedules_api import ScheduleIn, TikTokOptionsIn, _create_one_schedule


class _ForbiddenPool:
    """Any DB statement proves the consent gate did not run first."""

    async def fetchrow(self, *args, **kwargs):
        raise AssertionError("the human-consent gate must refuse before DB access")

    async def fetch(self, *args, **kwargs):
        raise AssertionError("the human-consent gate must refuse before DB access")

    async def fetchval(self, *args, **kwargs):
        raise AssertionError("the human-consent gate must refuse before DB access")

    async def execute(self, *args, **kwargs):
        raise AssertionError("the human-consent gate must refuse before DB access")


class _NoOfferPool:
    """Offer lookup returns nothing: the request PASSED the gate and proceeded
    into ordinary (fail-closed) offer validation."""

    async def fetchrow(self, *args, **kwargs):
        return None

    async def fetch(self, *args, **kwargs):
        return []

    async def fetchval(self, *args, **kwargs):
        return None

    async def execute(self, *args, **kwargs):
        return None


def _schedule(*, platform="tiktok", consent=None):
    return ScheduleIn(
        platform=platform,
        local_time=datetime(2027, 6, 2, 13, tzinfo=timezone.utc),
        tiktok=TikTokOptionsIn(consent=consent) if consent is not None else None,
    )


@pytest.mark.parametrize("machine_actor", [
    "system:worker",       # worker credential, default attribution (P1-1)
    "system:service",      # service credential (workers without own token)
    "automation:schedule", # an explicitly authorized automation stage
])
def test_machine_actor_cannot_record_tiktok_consent(machine_actor):
    """A machine credential cannot claim a person's Music Usage / Branded
    Content consent — refused before ANY database access."""
    with pytest.raises(HTTPException) as refused:
        asyncio.run(_create_one_schedule(
            _ForbiddenPool(), uuid.uuid4(), _schedule(consent=True),
            actor=machine_actor,
        ))
    assert refused.value.status_code == 403
    assert "consent" in refused.value.detail
    assert "human" in refused.value.detail


def test_human_actor_with_consent_proceeds_to_normal_gates():
    """A human reviewer (bound reviewer token) consenting is the intended
    flow: the request passes the attribution gate into the ordinary
    release-gate validation (here: the offer does not exist → 404)."""
    with pytest.raises(HTTPException) as missing:
        asyncio.run(_create_one_schedule(
            _NoOfferPool(), uuid.uuid4(), _schedule(consent=True),
            actor="Kashi",
        ))
    assert missing.value.status_code == 404  # offer not found — gate passed


def test_machine_actor_without_consent_is_not_refused():
    """Machine-created drafts remain available (consent: false) — automation
    is only denied the HUMAN attestation, not schedule creation."""
    with pytest.raises(HTTPException) as missing:
        asyncio.run(_create_one_schedule(
            _NoOfferPool(), uuid.uuid4(), _schedule(), actor="system:worker",
        ))
    assert missing.value.status_code == 404  # gate passed; ordinary 404

    with pytest.raises(HTTPException) as other_platform:
        asyncio.run(_create_one_schedule(
            _NoOfferPool(), uuid.uuid4(), _schedule(platform="youtube"),
            actor="system:worker",
        ))
    assert other_platform.value.status_code == 404


def test_dev_open_default_actor_still_records_consent():
    """Dev-open mode (explicit opt-in) keeps the historical body/default
    fallback: the route's default "reviewer" remains a human-sounding actor,
    which is acceptable exactly because no credential boundary exists."""
    with pytest.raises(HTTPException) as missing:
        asyncio.run(_create_one_schedule(
            _NoOfferPool(), uuid.uuid4(), _schedule(consent=True),
            actor="reviewer",
        ))
    assert missing.value.status_code == 404
