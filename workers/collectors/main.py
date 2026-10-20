"""Collector worker — RSS/Atom, GitHub releases, official page monitoring.

Week 2 target (master plan §18): a candidate appears once with canonical URL,
timestamp, and deduplication key.

Best practices applied here:
- Respect robots.txt and per-site rate limits.
- Deduplicate via (source_id, external_item_id) and normalized text hash.
- Idempotency: re-running a poll must never create duplicate items.
"""

import asyncio

POLL_INTERVAL_SECONDS = 6 * 60 * 60  # default polling cadence (source-configurable)


async def poll_source(source: dict) -> int:
    """Poll one registered source. Returns number of NEW items created.

    TODO(week-2):
    1. Load source config (adapter, feed URL, country scope) from the API.
    2. Fetch with respectful rate limiting and a source-tagged User-Agent.
    3. Normalize text → sha256 → text_hash.
    4. Resolve canonical URL; assign duplicate_group when seen across sources.
    5. INSERT ... ON CONFLICT (source_id, external_item_id) DO NOTHING.
    6. Log failures to structured logs; never crash the loop on one bad source.
    """
    raise NotImplementedError("adapter not implemented yet")


async def main() -> None:
    while True:
        # TODO(week-2): fetch enabled sources; group by adapter; poll concurrently
        # with per-domain semaphores; update sources.last_checked_at.
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
