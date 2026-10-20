"""Verification worker — structured extraction and evidence snapshots.

Weeks 3-4 target (master plan §18): every verified field links to evidence;
unverified records cannot enter script generation.

Hard rules (master plan §3):
- The LLM is an extractor/comparator, NEVER the evidence source.
- Each extracted field stores its supporting source URL, quote, hash, confidence.
- "Verified" requires ≥1 official source; high-impact claims want 2.
"""

import hashlib


def content_hash(raw: bytes) -> str:
    """Immutable fingerprint of captured evidence content."""
    return hashlib.sha256(raw).hexdigest()


async def verify_offer(offer_id: str) -> str:
    """Run the verification pipeline for one offer. Returns the new state.

    TODO(weeks 3-4):
    1. Load candidate offer + its source items.
    2. Provider-domain check: domain + account handle belong to the provider.
    3. Fetch official page snapshot (URL, timestamp, excerpt, content_hash).
    4. LLM structured extraction → offer fields, each mapped to its evidence.
    5. Conflict detection across sources; staleness check (recheck_at, expires_at).
    6. Transition state via the API state machine (packages/offer-schema).
    """
    raise NotImplementedError("verification pipeline not implemented yet")


async def main() -> None:
    # TODO: consume from queue (Redis + BullMQ or a durable workflow engine)
    raise NotImplementedError("worker loop not implemented yet")


if __name__ == "__main__":
    main()
