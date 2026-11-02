"""Release gate thumbnail parity (2026-10-23 review P2, closed 2026-11-02):
the gate recomputes the text the renderer draws from the CURRENT offer and
fact pack, so it can refuse an approved cover whose wording no longer
matches what the viewer would see."""

import asyncio
import json

from release_gate import _drawn_thumbnail_text


class _Pool:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, query, *args):
        return self.row


def _drawn(row):
    return asyncio.run(_drawn_thumbnail_text(_Pool(row), "off-1"))


def test_drawn_text_follows_the_current_offer_and_fact_pack():
    row = {"title": "A very long descriptive runtime title", "promo_code": "SAVE2026",
           "value": json.dumps({"amount": 12, "currency": "credits"}), "fact_pack": None}
    assert _drawn(row) == "12 CREDITS"
    row["fact_pack"] = json.dumps({"value": {"status": "contradicted"}})
    assert _drawn(row) == "SAVE2026"


def test_missing_offer_yields_no_drawn_text():
    assert _drawn(None) is None
