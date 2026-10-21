"""Verification worker — the verification desk pipeline (Weeks 3-4).

Flow per candidate offer (master plan §3, §18):
  1. Build the provider-domain allowlist from the source registry.
     Offers whose provider has NO registered Tier-A sources are skipped —
     "register the official source first" is the system's answer, not scraping.
  2. Capture each of the provider's registered page_watch pages → POST as
     immutable OFFICIAL evidence (server checks the domain allowlist).
  3. Structured extraction (rules + optional LLM) → POST /extraction; every
     field carries its evidence URL + excerpt + confidence; disagreements
     between the two extractors become conflicts for reviewer triage.
  4. Advance the state machine: candidate → evidence_needed → (attempt) verified.
     The API re-checks every gate server-side; unverified offers can NEVER
     enter script generation.

API is the source of truth — the worker holds no durable state.
"""

import asyncio
import logging
import os
import sys
import time

import httpx

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))
sys.path.insert(0, os.path.dirname(__file__))

from source_adapters import Fetcher, fetch_page_snapshot  # noqa: E402

from allowlist import build_allowlist  # noqa: E402
from extractors import extract, is_complete  # noqa: E402

API_URL = os.environ.get("API_URL", "http://localhost:8000")
SWEEP_INTERVAL = 120  # seconds
VERIFY_STATES = ("candidate", "evidence_needed")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("verification")


class Verifier:
    def __init__(self, api_url: str = API_URL):
        self.api_url = api_url.rstrip("/")
        self.client = httpx.Client(timeout=30)
        self.fetcher = Fetcher(timeout=25.0, min_interval=3.0)

    # ------------------------------------------------------------- API I/O

    def _get(self, path: str, **kwargs) -> dict | list:
        resp = self.client.get(f"{self.api_url}{path}", **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json: dict) -> httpx.Response:
        return self.client.post(f"{self.api_url}{path}", json=json)

    def run_forever(self) -> None:
        log.info("verification worker started against %s", self.api_url)
        while True:
            try:
                asyncio.run(self.sweep())
                time.sleep(SWEEP_INTERVAL)
            except httpx.HTTPError as exc:
                log.error("API unreachable, retrying in %ss: %s", SWEEP_INTERVAL, exc)
                time.sleep(SWEEP_INTERVAL)
            except Exception:  # noqa: BLE001
                log.exception("sweep failed; retrying")
                time.sleep(SWEEP_INTERVAL)

    async def sweep(self) -> None:
        offers = self._get("/offers", params={"limit": 100})
        targets = [o for o in offers if o.get("state") in VERIFY_STATES]
        if targets:
            log.info("verifying %d offer(s)", len(targets))

        allowlist = build_allowlist(self._get("/sources"))

        for offer in targets:
            try:
                await asyncio.to_thread(self.verify_offer, offer, allowlist)
            except Exception:  # noqa: BLE001 — one bad offer never stops the sweep
                log.exception("verification failed for offer %s", offer.get("id"))

        # Correction workflow: expired deals pause, overdue rechecks demote.
        result = self._post("/offers/sweep-stale", json={}).json()
        if result.get("expired") or result.get("recheck_queued"):
            log.info("stale sweep: %s", result)

    # ------------------------------------------------------------ pipeline

    def verify_offer(self, offer: dict, allowlist: dict) -> None:
        offer_id = offer["id"]
        provider = offer.get("provider") or ""

        official_urls = self._official_pages(provider, allowlist)
        if not official_urls:
            log.warning(
                "offer %s: provider '%s' has no registered page_watch sources — "
                "register the official source first (allowlist rule)",
                offer_id, provider,
            )
            return

        # candidate → evidence_needed (verification has begun)
        if offer.get("state") == "candidate":
            self._post(f"/offers/{offer_id}/transition",
                       json={"to": "evidence_needed", "note": "verification pipeline started"})

        # 2-3. capture official pages → evidence → extraction
        best_fields: dict = {}
        conflicts: list = []
        model_used = None
        for url in official_urls:
            self._capture_evidence(offer_id, url, provider)
            snapshot = fetch_page_snapshot(url, fetcher=self.fetcher)
            body = snapshot[0].text if snapshot else ""
            if not body:
                continue
            fields, page_conflicts, model_used = extract(body, url)
            if len(fields) > len(best_fields):
                best_fields = fields
            if page_conflicts:
                conflicts.extend(page_conflicts)

        complete = is_complete(best_fields)
        self._post(f"/offers/{offer_id}/extraction", json={
            "fields": best_fields,
            "complete": complete,
            "conflicts": conflicts,
            "model": model_used or "rules/0.1",
        })

        # 4. attempt promotion to verified — the API re-checks all gates.
        if complete and not conflicts:
            resp = self._post(f"/offers/{offer_id}/transition", json={
                "to": "verified",
                "note": "official evidence + complete extraction, no conflicts",
            })
            if resp.status_code == 200:
                log.info("offer %s VERIFIED (%d fields linked to evidence)",
                         offer_id, len(best_fields))
            else:
                log.warning("offer %s not verified yet: %s", offer_id, resp.text)
        else:
            log.info("offer %s stays evidence_needed: complete=%s conflicts=%d",
                     offer_id, complete, len(conflicts))

    # -------------------------------------------------------------- helpers

    def _official_pages(self, provider: str, allowlist: dict) -> list[str]:
        """Registered page_watch URLs belonging to the provider's domains."""
        sources = self._get("/sources")
        urls = []
        for s in sources:
            config = s.get("config") or {}
            if s.get("adapter") != "page_watch":
                continue
            if (s.get("provider") or "").strip().lower() != provider.strip().lower():
                continue
            url = config.get("url") or s.get("canonical_domain")
            if not url:
                continue
            from allowlist import domain_ok  # local import: module under test too

            if domain_ok(allowlist, provider, url):
                urls.append(url)
        return urls

    def _capture_evidence(self, offer_id: str, url: str, provider: str) -> None:
        """POST the page snapshot as OFFICIAL evidence. The API enforces the
        domain allowlist — an unregistered domain raises 422 and is logged."""
        try:
            snapshot = fetch_page_snapshot(url, fetcher=self.fetcher)
            item = snapshot[0]
            resp = self._post(f"/offers/{offer_id}/evidence", json={
                "url": url,
                "captured_content": item.text,
                "excerpt": item.title,
                "official": True,
                "supported_fields": ["expiry", "price", "eligibility", "promo_code", "renewal"],
            })
            if resp.status_code == 422:
                log.error("evidence rejected for offer %s (%s): %s",
                          offer_id, provider, resp.json().get("detail"))
        except Exception:  # noqa: BLE001
            log.exception("official page capture failed: %s", url)


def main() -> None:
    Verifier().run_forever()


if __name__ == "__main__":
    main()
