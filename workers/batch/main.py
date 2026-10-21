"""Batch worker — the nightly pipeline step (v0.19, master plan §10
"nightly batch: collect → verify → script", §18 week 10).

The pipeline's human gates are deliberate and stay human:
  - evidence review (§3)  — a human decides an offer is real
  - capture recording (§4) — the operator records on their own account
  - redaction review (§4) — a human attests the footage is clean
  - publish approval (§17) — a human approves the exact script version
Everything AROUND those gates is automatable, and this worker automates it:

  1. Script generation — deterministic (no LLM), so a verified offer with
     official evidence and no script gets one generated automatically.
  2. Readiness report — counts what is waiting on whom (verification desk,
     redaction reviews, render candidates, approvals, metrics backlog).

Usage:
    python main.py [--once] [--api http://localhost:8000] [--interval 900]
"""

import argparse
import logging
import os
import signal
import time

import httpx

API_URL_DEFAULT = os.environ.get("MTK_API_URL", "http://localhost:8000")

log = logging.getLogger("batch")

_API_TOKEN = os.environ.get("MTK_API_TOKEN", "").strip()


def _api_auth_headers() -> dict:
    """Authorization headers for the API when MTK_API_TOKEN is configured
    (services/api/api_hardening.py) — same contract as the other workers."""
    return {"Authorization": f"Bearer {_API_TOKEN}"} if _API_TOKEN else {}


class Batch:
    def __init__(self, api_url: str = API_URL_DEFAULT):
        self.api = httpx.Client(timeout=60, base_url=api_url.rstrip("/"),
                                headers=_api_auth_headers())

    # ------------------------------------------------------------- steps

    def generate_scripts(self) -> int:
        """One script per offer that has earned it: verified (or
        approved_for_video) + official evidence, and no script yet.

        The server re-checks the gate on every call (§3) — this worker only
        decides WHEN to ask, never WHETHER the offer qualifies.
        """
        created = 0
        for state in ("verified", "approved_for_video"):
            try:
                offers = self.api.get("/offers", params={"state": state, "limit": 200}).json()
            except httpx.HTTPError as exc:
                log.warning("offer list (%s) unavailable: %s", state, exc)
                continue
            for offer in offers:
                if not offer.get("official_evidence"):
                    continue  # no official evidence → nothing to script from
                try:
                    scripts = self.api.get(f"/offers/{offer['id']}/scripts").json()
                except httpx.HTTPError as exc:
                    log.warning("scripts for %s unavailable: %s", offer["id"], exc)
                    continue
                if scripts:
                    continue
                try:
                    resp = self.api.post(f"/offers/{offer['id']}/script",
                                         params={"created_by": "batch"})
                except httpx.HTTPError as exc:
                    log.warning("script generation for %s failed: %s", offer["id"], exc)
                    continue
                if resp.status_code == 201:
                    created += 1
                    log.info("script generated for offer %s (%s)", offer["id"], offer.get("title"))
                else:
                    log.info("script generation refused for %s (%s) — operator action needed",
                             offer["id"], resp.status_code)
        return created

    def readiness(self) -> dict:
        """What is waiting on whom — the operator's single status read-out."""
        out: dict = {}
        try:
            offers = self.api.get("/offers", params={"limit": 200}).json()
        except httpx.HTTPError as exc:
            log.warning("readiness: offer list unavailable: %s", exc)
            return out
        out["awaiting_verification"] = sum(
            1 for o in offers if o.get("state") == "evidence_needed")
        out["awaiting_correction_review"] = sum(
            1 for o in offers if o.get("state") == "corrected")

        try:
            captures = self.api.get("/captures", params={"limit": 200}).json()
        except httpx.HTTPError:
            captures = []
        out["captures_total"] = len(captures)
        out["captures_awaiting_redaction_review"] = sum(
            1 for c in captures if not c.get("redaction_reviewed"))

        try:
            candidates = self.api.get("/render-candidates", params={"limit": 200}).json()
        except httpx.HTTPError:
            candidates = []
        out["render_candidates"] = len(candidates)

        try:
            scheduled = self.api.get("/schedules", params={"state": "scheduled", "limit": 200}).json()
        except httpx.HTTPError:
            scheduled = []
        out["scheduled_posts"] = len(scheduled)
        return out

    def run_once(self) -> dict:
        created = self.generate_scripts()
        report = self.readiness()
        report["scripts_created"] = created
        log.info("batch complete: %s", report)
        return report

    def run_forever(self, interval: int) -> None:
        gap = int(os.environ.get("MTK_BATCH_INTERVAL", str(interval)))
        while not _STOP:
            started = time.monotonic()
            try:
                self.run_once()
            except httpx.HTTPError as exc:
                log.warning("batch aborted (API unreachable): %s", exc)
            if _STOP:
                break
            elapsed = time.monotonic() - started
            time.sleep(max(5, gap - elapsed))


# ---------------------------------------------------------- graceful stop
# SIGTERM (docker stop / systemd) must NOT abandon a post mid-upload: the
# worker finishes the item it is on, reports the outcome, then exits.
_STOP = False


def _install_stop_handlers() -> None:
    def _handler(signum, _frame):
        global _STOP
        _STOP = True
        log.info("signal %s received — finishing the current item, then exiting", signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):  # pragma: no cover — non-main thread
            pass


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="MTK RADAR batch worker")
    parser.add_argument("--once", action="store_true", help="run one batch and exit")
    parser.add_argument("--api", default=API_URL_DEFAULT)
    parser.add_argument("--interval", type=int, default=900)
    args = parser.parse_args()

    _install_stop_handlers()
    batch = Batch(args.api)
    if args.once:
        batch.run_once()
        return
    batch.run_forever(args.interval)


if __name__ == "__main__":
    main()
