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
import json
import logging
import os
import sys
import time

import httpx


_API_TOKEN = (os.environ.get("MTK_WORKER_TOKEN")
              or os.environ.get("MTK_API_TOKEN") or "").strip()

def _api_auth_headers() -> dict:
    """Authorization headers for the API when MTK_API_TOKEN is configured
    (services/api/api_hardening.py). Empty dict = open local dev API."""
    return {"Authorization": f"Bearer {_API_TOKEN}"} if _API_TOKEN else {}
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))
# The signing helper lives beside the API so both sides share one implementation.
# Inserted before the worker directory so worker modules keep precedence.
sys.path.insert(0, os.path.join(REPO_ROOT, "services", "api"))
sys.path.insert(0, os.path.dirname(__file__))

from api_paging import iter_pages  # noqa: E402
from source_adapters import Fetcher, check_robots, fetch_page_snapshot  # noqa: E402
from source_adapters.egress import EgressPolicy  # noqa: E402
from document_sections import (  # noqa: E402
    MAX_DOCUMENT_CHARS,
    MAX_SECTION_CHARS,
    SECTIONS_VERSION,
)
from fetch_attestation import sign_provenance  # noqa: E402

from allowlist import build_allowlist, domain_ok, host_of  # noqa: E402
from extractors import extract_document, is_complete  # noqa: E402
from worker_heartbeat import WorkerHeartbeat  # noqa: E402

API_URL = os.environ.get("API_URL", "http://localhost:8000")
SWEEP_INTERVAL = 120  # seconds
VERIFY_STATES = ("candidate", "evidence_needed")
#: Recorded with every snapshot so a reviewer can see which process fetched it.
FETCH_IDENTITY = os.environ.get("MTK_FETCH_IDENTITY", "verification-worker")
#: HMAC key shared with the API. Without it the API rejects machine evidence;
#: a signature attests the key holder produced the record, not that the fetch
#: happened (see services/api/fetch_attestation.py).
FETCH_SIGNING_KEY = os.environ.get("MTK_FETCH_SIGNING_KEY", "").strip()
#: A source may only be read when a human has recorded that its terms permit
#: automated reading. robots.txt is checked separately at fetch time.
TOS_ATTESTATION_REQUIRED = os.environ.get(
    "MTK_REQUIRE_TOS_ATTESTATION", "1",
).strip().lower() not in {"0", "false", "no", "off"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("verification")


class Verifier:
    def __init__(self, api_url: str = API_URL):
        self.api_url = api_url.rstrip("/")
        self.client = httpx.Client(timeout=30, headers=_api_auth_headers())
        self.fetcher = Fetcher(timeout=25.0, min_interval=3.0)
        # Verification fetches are HTTPS-only, public-address-only, hop-validated
        # and bounded (master plan §6 step 2, audit A19).
        self.policy = EgressPolicy()
        if not FETCH_SIGNING_KEY:
            log.warning(
                "MTK_FETCH_SIGNING_KEY is not set — the API will reject unsigned "
                "machine evidence"
            )
        elif len(FETCH_SIGNING_KEY) < 32:
            log.error(
                "MTK_FETCH_SIGNING_KEY is shorter than 32 characters — signing "
                "will fail and no evidence will be accepted"
            )

    # ------------------------------------------------------------- policy

    def _load_policy(self) -> dict | None:
        """The operator's automation policy. None means the endpoint is
        unavailable — autonomous state changes then fail closed (evidence is
        still collected, but nothing is promoted without a human)."""
        try:
            resp = self.client.get(f"{self.api_url}/automation/policy")
            if resp.status_code != 200:
                return None
            return (resp.json() or {}).get("policy")
        except (httpx.HTTPError, ValueError):
            return None

    @staticmethod
    def _stage_auto(policy: dict | None, stage: str) -> bool:
        if not policy:
            return False
        if policy.get("paused") or policy.get("dry_run"):
            return False
        return ((policy.get("stages") or {}).get(stage)) == "auto"

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
        policy = self._load_policy()
        if policy is not None and not self._stage_auto(policy, "verify"):
            state = "paused" if policy.get("paused") else (
                "dry-run" if policy.get("dry_run") else "human-controlled")
            log.info("verification stage is %s in Settings — collecting nothing, "
                     "leaving offers for a human", state)
            # expiry/overdue safety still runs: it can only pause or demote.
            self._post("/offers/sweep-stale", json={})
            return

        offers = list(iter_pages(self.client, f"{self.api_url}/offers", limit=100))
        targets = [o for o in offers if o.get("state") in VERIFY_STATES]
        if targets:
            log.info("verifying %d offer(s)", len(targets))

        allowlist = build_allowlist(self._get("/sources"))

        for offer in targets:
            try:
                await asyncio.to_thread(self.verify_offer, offer, allowlist, policy)
            except Exception:  # noqa: BLE001 — one bad offer never stops the sweep
                log.exception("verification failed for offer %s", offer.get("id"))

        # Correction workflow: expired deals pause, overdue rechecks demote.
        result = self._post("/offers/sweep-stale", json={}).json()
        if result.get("expired") or result.get("recheck_queued"):
            log.info("stale sweep: %s", result)

    # ------------------------------------------------------------ pipeline

    def verify_offer(self, offer: dict, allowlist: dict,
                     policy: dict | None = None) -> None:
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
            response = self._post(f"/offers/{offer_id}/transition",
                                  json={"to": "evidence_needed", "note": "verification pipeline started"})
            response.raise_for_status()

        # 2-3. capture official pages → evidence → extraction
        best_fields: dict = {}
        conflicts: list = []
        model_used = None
        observed_values: dict[str, str] = {}
        usable_pages = 0
        #: Sections examined per evidence row. The API recomputes this from the
        #: stored snapshot text, so a truncated read is rejected, not trusted.
        sections_by_evidence: dict[str, int] = {}
        for url, source_id in official_urls:
            # Permission first (master plan §3): a page may only be read when
            # the host's robots policy is readable and permits it. The decision
            # is recorded with the evidence, not inferred later.
            permission = self._permission(url)
            if not permission.allowed:
                log.warning(
                    "offer %s: %s — not fetching %s",
                    offer_id, permission.reason, url,
                )
                continue
            snapshot = fetch_page_snapshot(
                url, fetcher=self.fetcher, max_text_chars=None, policy=self.policy,
            )
            if not snapshot or not snapshot[0].text:
                continue
            item = snapshot[0]
            # Never certify a provider URL that redirected to a different owner.
            if not domain_ok(allowlist, provider, item.url):
                raise ValueError("official page redirected outside the provider allowlist")
            provenance = item.extra.get("provenance")
            if provenance and not 200 <= provenance["http_status"] < 300:
                # An outage or challenge means "unavailable", never proof the
                # offer ended or is valid (§6 step 2). Do not store the error
                # page as if it were the provider's terms.
                log.warning(
                    "offer %s: %s returned HTTP %s — treated as unavailable, not as terms",
                    offer_id, item.url, provenance["http_status"],
                )
                continue
            if len(item.text) > MAX_DOCUMENT_CHARS:
                # Refusing is honest; cutting the document is not. The egress
                # bound normally makes this unreachable.
                raise ValueError(
                    "official snapshot exceeds the sectioned-processing ceiling; "
                    "review rather than truncate terms"
                )
            fields, page_conflicts, page_model, sections_total = extract_document(
                item.text, item.url,
            )
            payload = {
                "url": item.url, "source_id": source_id,
                "captured_content": item.text,
                "excerpt": item.title, "official": True,
                "supported_fields": sorted(fields),
            }
            # Exact bytes + how they were fetched. The API re-hashes and
            # re-checks every URL in the chain; it never trusts these.
            if provenance:
                provenance = {
                    **provenance,
                    "fetch_identity": FETCH_IDENTITY,
                    "robots": permission.as_provenance(),
                }
                if FETCH_SIGNING_KEY:
                    provenance["signature"] = sign_provenance(
                        provenance, FETCH_SIGNING_KEY,
                    )
                payload["raw_content_b64"] = item.extra["raw_content_b64"]
                payload["provenance"] = provenance
            evidence = self._post(f"/offers/{offer_id}/evidence", json=payload)
            evidence.raise_for_status()
            evidence_id = evidence.json()["id"]  # duplicates return the same identity
            usable_pages += 1
            sections_by_evidence[evidence_id] = sections_total
            for field in fields.values():
                field["evidence_id"] = evidence_id
            # Retain disagreement across official pages rather than picking the
            # most attractive source. The server also checks every quote/value.
            for name, field in fields.items():
                value = str(field["value"]).strip().casefold()
                if name in observed_values and observed_values[name] != value:
                    conflicts.append({"field": name, "reason": "official pages disagree"})
                observed_values.setdefault(name, value)
            if (is_complete(fields), len(fields)) > (is_complete(best_fields), len(best_fields)):
                best_fields = fields
                model_used = page_model
            if page_conflicts:
                conflicts.extend(page_conflicts)

        if usable_pages == 0:
            # Nothing was actually read. Posting an empty extraction would
            # overwrite a previous truthful proposal with silence.
            log.warning("offer %s: no official page was readable; leaving evidence_needed", offer_id)
            return

        response = self._post(f"/offers/{offer_id}/extraction", json={
            "fields": best_fields,
            "conflicts": conflicts,
            "model": model_used or "rules/0.1",
            # Everything the verifier actually read, section by section.
            "coverage": {
                "version": SECTIONS_VERSION,
                "sections_total": sum(sections_by_evidence.values()),
                "max_section_chars": MAX_SECTION_CHARS,
                "evidence_ids": list(sections_by_evidence),
            },
        })
        response.raise_for_status()
        complete = response.json().get("complete") is True

        # 4. attempt promotion to verified — the API re-checks all gates.
        if complete and not conflicts:
            # Fail closed: if the policy could not be read we still preserve the
            # evidence, but only a named human may promote the offer.
            auto = policy is not None and self._stage_auto(policy, "verify")
            if not auto:
                log.info("offer %s is ready — waiting for a human reviewer "
                         "(verify stage is human-controlled or policy unreadable)", offer_id)
                return
            resp = self._post(f"/offers/{offer_id}/transition", json={
                "to": "verified",
                "reviewer": "automation:verify",
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

    def _permission(self, url: str):
        """Per-host robots decision, cached for the life of one worker run."""
        cache = getattr(self, "_permission_cache", None)
        if cache is None:
            cache = self._permission_cache = {}
        host = host_of(url)
        if host not in cache:
            cache[host] = check_robots(host, fetcher=self.fetcher, policy=self.policy)
        return cache[host]

    def _official_pages(self, provider: str, allowlist: dict) -> list[tuple[str, str]]:
        """Registered page_watch URLs and their source id, for the provider.

        A source without a recorded terms-of-service review is not read: robots
        permission is necessary but is not contractual consent (slice 10).
        """
        sources = self._get("/sources")
        pages: list[tuple[str, str]] = []
        for s in sources:
            if not s.get("enabled") or s.get("trust_tier") != "A_provider_owned":
                continue
            config = s.get("config") or {}
            if isinstance(config, str):
                config = json.loads(config)
            if s.get("adapter") != "page_watch":
                continue
            if (s.get("provider") or "").strip().lower() != provider.strip().lower():
                continue
            attested = s.get("tos_valid")
            if attested is None:
                # Older API: a timestamp with no expiry is still better than
                # reading without any recorded review.
                attested = bool(s.get("tos_reviewed_at"))
            if TOS_ATTESTATION_REQUIRED and not attested:
                log.warning(
                    "source %s (%s) has no current terms-of-service review — "
                    "not fetching", s.get("id"), s.get("provider"),
                )
                continue
            url = config.get("url") or s.get("canonical_domain")
            if not url:
                continue
            if domain_ok(allowlist, provider, url):
                pages.append((url, s["id"]))
        return pages


def main() -> None:
    hb = WorkerHeartbeat(API_URL, "verification")
    hb.start()
    try:
        Verifier().run_forever()
    finally:
        hb.stop()


if __name__ == "__main__":
    main()
