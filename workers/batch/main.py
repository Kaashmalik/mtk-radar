"""Batch worker — the periodic pipeline step (v0.19, master plan §10
"nightly batch: collect → verify → script", §18 week 10).

The pipeline's human gates are deliberate and stay human:
  - evidence review (§3)  — a human decides an offer is real
  - capture recording (§4) — the operator records on their own account
  - redaction review (§4) — a human attests the footage is clean
  - publish approval (§17) — a human approves the exact script version
Everything AROUND those gates is automatable, and this worker automates it:

  1. Trend radar scan — the durable `trend_scan` job claims this worker;
     a cadence fallback keeps the radar alive when the queue is unavailable.
  2. Script generation — deterministic (no LLM), so a verified offer with
     official evidence and no script gets one generated automatically.
  3. Readiness report — counts what is waiting on whom (verification desk,
     redaction reviews, render candidates, approvals, metrics backlog).

Usage:
    python main.py [--once] [--api http://localhost:8000] [--interval 900]
"""

import argparse
import logging
import os
import signal
import sys
import time
from typing import Optional

import httpx

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))

from api_paging import fetch_all  # noqa: E402
from worker_heartbeat import WorkerHeartbeat  # noqa: E402

API_URL_DEFAULT = os.environ.get("MTK_API_URL", "http://localhost:8000")

#: The Trend Radar v2 re-scan cadence. The durable `trend_scan` job (armed by
#: migration 032) is the primary trigger; this cadence is the fail-open
#: fallback when the job queue is unreachable or predates it.
TREND_SCAN_INTERVAL_S = max(300, int(os.environ.get("MTK_TREND_SCAN_INTERVAL_S", "1800")))

log = logging.getLogger("batch")

_API_TOKEN = (os.environ.get("MTK_WORKER_TOKEN")
              or os.environ.get("MTK_API_TOKEN") or "").strip()


def _api_auth_headers() -> dict:
    """Authorization headers for the API when MTK_API_TOKEN is configured
    (services/api/api_hardening.py) — same contract as the other workers."""
    return {"Authorization": f"Bearer {_API_TOKEN}"} if _API_TOKEN else {}


class Batch:
    def __init__(self, api_url: str = API_URL_DEFAULT):
        self.api = httpx.Client(timeout=60, base_url=api_url.rstrip("/"),
                                headers=_api_auth_headers())
        self._scan_due = 0.0  # monotonic deadline for the fallback cadence scan

    # ------------------------------------------------------------ policy

    def _load_policy(self) -> Optional[dict]:
        """Read the operator's automation policy. Missing endpoint = legacy
        behaviour for script generation and no unattended approval."""
        try:
            resp = self.api.get("/automation/policy")
            if getattr(resp, "status_code", 200) >= 300:
                return None
            body = resp.json() or {}
            return body.get("policy") or None
        except Exception as exc:  # noqa: BLE001 — an old/unreachable API
            log.warning("automation policy unavailable, using conservative defaults: %s", exc)
            return None

    @staticmethod
    def _stage_auto(policy: Optional[dict], stage: str, *, default: bool = False) -> bool:
        if policy is None:
            return default
        if policy.get("paused") or policy.get("dry_run"):
            return False
        return (policy.get("stages") or {}).get(stage) == "auto"

    @staticmethod
    def _limits(policy: Optional[dict]) -> dict:
        return (policy or {}).get("guardrails") or {}

    # ----------------------------------------------------- trend radar v2

    def scan_trends_once(self) -> bool:
        """One radar scan + report. The API re-checks everything; this worker
        only decides WHEN, never WHETHER an item is worth a video."""
        ok = False
        detail = None
        try:
            resp = self.api.post("/trends/scan", params={"limit": 200})
            ok = resp.status_code < 300
            if ok:
                body = resp.json() or {}
                log.info("trend scan: +%d new, %d updated, %d re-scored",
                         body.get("created", 0), body.get("updated", 0),
                         body.get("rescored", 0))
            else:
                detail = f"scan refused: HTTP {resp.status_code}"[:1900]
        except (httpx.HTTPError, ValueError) as exc:
            detail = f"scan failed: {exc}"[:1900]
        # Report the outcome either way: a healthy scan re-arms the recurring
        # `trend_scan` job at its interval; a failed one retries in 300s
        # (research the dead-letter in /attention after 5 straight failures).
        try:
            self.api.post("/trends/scan-result",
                          json={"ok": ok, "detail": detail})
        except httpx.HTTPError:
            log.warning("could not report trend scan result")
        return ok

    def _claim_trend_scan(self) -> str:
        """"claimed" / "empty" / "unavailable" — mirrors the collector."""
        try:
            resp = self.api.post(
                "/jobs/claim",
                json={"worker": "batch", "lease_s": 900, "kinds": ["trend_scan"]},
            )
        except httpx.HTTPError:
            return "unavailable"
        if resp.status_code == 404:
            return "unavailable"  # older API without the job queue
        if resp.status_code >= 300:
            return "unavailable"
        try:
            body = resp.json()
        except ValueError:
            return "unavailable"
        return "claimed" if body.get("claimed") else "empty"

    def maybe_scan_trends(self, policy: Optional[dict]) -> bool:
        """Job-driven first (durable owed work), then the cadence fallback for
        an API that predates the queue.

        Trend scanning is Tier-B signal intake: it honors the `collect` stage
        (auto by default when no policy exists) and stops for paused/dry-run
        like every other unattended step — a manual operator scans explicitly
        from the dashboard instead."""
        if not self._stage_auto(policy, "collect", default=True):
            return False
        state = self._claim_trend_scan()
        if state == "claimed":
            return self.scan_trends_once()
        if state == "empty":
            return False  # the queue says the next scan is not due yet
        now_m = time.monotonic()
        if now_m < self._scan_due:
            return False
        self._scan_due = now_m + TREND_SCAN_INTERVAL_S
        return self.scan_trends_once()

    def expire_queue(self, policy: Optional[dict]) -> int:
        """Self-archive stale production-queue rows (offer expired, deadline
        passed, or the trend cooled for 7 days). Read-only housekeeping with
        a server-side reason attached — never touches a human gate."""
        if not self._stage_auto(policy, "collect", default=True):
            return 0
        try:
            resp = self.api.post("/production-queue/expire")
            if resp.status_code >= 300:
                log.warning("queue expiry refused: HTTP %s", resp.status_code)
                return 0
            return int((resp.json() or {}).get("expired", 0))
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("queue expiry skipped: %s", exc)
            return 0

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
                offers = fetch_all(self.api, "/offers", {"state": state}, limit=200)
            except (httpx.HTTPError, ValueError) as exc:
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

    def approve_offers(self, policy: dict) -> int:
        """Autopilot 'approve' stage: verified offers with a complete package
        become approved_for_video. The API is the authority and can still say
        no (render/redaction/hash/unsafe-command gates)."""
        limits = self._limits(policy)
        requires_render = limits.get("auto_approve_requires_render", True)
        approved = 0
        try:
            offers = fetch_all(self.api, "/offers", {"state": "verified"}, limit=200)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("approve stage: offer list unavailable: %s", exc)
            return 0

        for offer in offers:
            if (offer.get("correction_note") or "").strip():
                log.info("offer %s has an open correction note — human review required",
                         offer["id"])
                continue
            if requires_render:
                try:
                    # Existence only: one row is enough, and a fixed default
                    # page could miss the render entirely on a busy offer.
                    renders = self.api.get(
                        "/renders", params={"offer_id": offer["id"], "limit": 1}
                    ).json()
                except httpx.HTTPError:
                    renders = []
                if not renders:
                    log.info("offer %s is verified but has no render — waiting on the "
                             "render stage before unattended approval", offer["id"])
                    continue
            try:
                resp = self.api.post(
                    f"/offers/{offer['id']}/transition",
                    json={"to": "approved_for_video",
                          "reviewer": "automation:approve",
                          "note": "autopilot: verified offer with a complete render package"},
                )
            except httpx.HTTPError as exc:
                log.warning("auto-approval for %s failed: %s", offer["id"], exc)
                continue
            if getattr(resp, "status_code", 500) == 200:
                approved += 1
                log.info("offer %s AUTO-APPROVED for video (autopilot)", offer["id"])
            else:
                detail = ""
                try:
                    detail = (resp.json() or {}).get("detail", "")
                except Exception:  # noqa: BLE001
                    detail = getattr(resp, "text", "")
                log.info("auto-approval refused for %s (%s): %s",
                         offer["id"], resp.status_code, detail)
        return approved

    def schedule_approved(self, policy: dict) -> int:
        """Autopilot 'schedule' stage: approved offers get per-platform queue
        entries at the next configured publish window, approved with the
        automation identity. Budget + hash + offer gates are re-checked by the
        API; a 429 stops the stage for the day."""
        limits = self._limits(policy)
        platforms = limits.get("auto_schedule_platforms") or ["youtube"]
        try:
            offers = fetch_all(self.api, "/offers",
                               {"state": "approved_for_video"}, limit=200)
            schedules = fetch_all(self.api, "/schedules", limit=500)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("schedule stage unavailable: %s", exc)
            return 0

        # Dedupe the TARGET, not just the platform. A schedule for account A /
        # language en must not suppress account B or an Urdu variant — the
        # same one-variant-suppresses-another bug the render queue had.
        def target_key(schedule: dict) -> tuple:
            return (
                str(schedule.get("platform") or ""),
                str(schedule.get("platform_account_id") or ""),
                str(schedule.get("language") or ""),
                str(schedule.get("content_variant_id") or ""),
                str(schedule.get("metadata_variant") or ""),
            )

        by_offer: dict[str, set[tuple]] = {}
        for schedule in schedules:
            by_offer.setdefault(str(schedule.get("offer_id")), set()).add(
                target_key(schedule))

        created = 0
        for offer in offers:
            existing = by_offer.get(str(offer["id"]), set())
            for platform in platforms:
                # The autopilot's default target is the unpinned/English one.
                if (platform, "", "", "", "") in existing:
                    continue  # never queue the same target twice for one offer
                try:
                    slot = self.api.get("/automation/next-slot",
                                        params={"platform": platform}).json()
                    resp = self.api.post(
                        f"/offers/{offer['id']}/schedules",
                        json={
                            "platform": slot["platform"],
                            "local_time": slot["local_time"],
                            "timezone": slot.get("timezone", "Asia/Karachi"),
                            "privacy": slot.get("privacy", "private"),
                        },
                    )
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    log.warning("schedule creation for %s/%s failed: %s",
                                offer["id"], platform, exc)
                    continue

                if getattr(resp, "status_code", 500) not in (200, 201):
                    detail = ""
                    try:
                        detail = (resp.json() or {}).get("detail", "")
                    except Exception:  # noqa: BLE001
                        detail = getattr(resp, "text", "")
                    log.info("schedule creation refused for %s/%s (%s): %s",
                             offer["id"], platform, resp.status_code, detail)
                    continue

                body = {}
                try:
                    body = resp.json() or {}
                except Exception:  # noqa: BLE001
                    body = {}
                schedule_id = body.get("id")
                state = body.get("state", "draft")
                if not schedule_id:
                    continue
                if not self._advance(schedule_id, state, platform):
                    return created  # budget exhausted / gate refused
                if not body.get("created", True):
                    # idempotent re-submit: it already existed, don't count it
                    continue
                created += 1
                log.info("offer %s AUTO-SCHEDULED on %s (autopilot, %s)",
                         offer["id"], platform, body.get("state", "scheduled"))
                existing.add(platform)
        return created

    def _advance(self, schedule_id: str, state: str, platform: str) -> bool:
        """Walk a freshly created schedule to 'scheduled' through the API.
        Returns False when the server says stop (budget/gate refusal)."""
        steps = []
        if state == "draft":
            steps.append(("needs_approval", None))
        if state in ("draft", "needs_approval"):
            steps.append(("approved", "automation:approve"))
        if state in ("draft", "needs_approval", "approved"):
            steps.append(("scheduled", "automation:schedule"))

        for target, actor in steps:
            payload = {"to": target, "note": f"autopilot schedule ({platform})"}
            if actor:
                payload["reviewer"] = actor
            try:
                resp = self.api.post(f"/schedules/{schedule_id}/transition", json=payload)
            except httpx.HTTPError as exc:
                log.warning("schedule %s -> %s failed: %s", schedule_id, target, exc)
                return False
            if getattr(resp, "status_code", 500) != 200:
                detail = ""
                try:
                    detail = (resp.json() or {}).get("detail", "")
                except Exception:  # noqa: BLE001
                    detail = getattr(resp, "text", "")
                level = log.info if resp.status_code == 429 else log.warning
                level("schedule %s cannot advance to %s (%s): %s",
                      schedule_id, target, resp.status_code, detail)
                return resp.status_code != 429
        return True

    def readiness(self) -> dict:
        """What is waiting on whom — the operator's single status read-out."""
        out: dict = {}
        try:
            offers = fetch_all(self.api, "/offers", limit=200)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("readiness: offer list unavailable: %s", exc)
            return out
        out["awaiting_verification"] = sum(
            1 for o in offers if o.get("state") == "evidence_needed")
        out["awaiting_correction_review"] = sum(
            1 for o in offers if o.get("state") == "corrected")

        try:
            captures = fetch_all(self.api, "/captures", limit=200)
        except (httpx.HTTPError, ValueError):
            captures = []
        out["captures_total"] = len(captures)
        out["captures_awaiting_redaction_review"] = sum(
            1 for c in captures if not c.get("redaction_reviewed"))

        try:
            candidates = fetch_all(self.api, "/render-candidates", limit=200)
        except (httpx.HTTPError, ValueError):
            candidates = []
        out["render_candidates"] = len(candidates)

        try:
            scheduled = fetch_all(self.api, "/schedules",
                                  {"state": "scheduled"}, limit=200)
        except (httpx.HTTPError, ValueError):
            scheduled = []
        out["scheduled_posts"] = len(scheduled)
        return out

    def run_once(self) -> dict:
        policy = self._load_policy()
        if policy is not None and policy.get("paused"):
            log.info("automation is PAUSED in Settings — batch performs no state changes")
            return {"paused": True, "scripts_created": 0,
                    "offers_auto_approved": 0, "posts_auto_scheduled": 0}

        started_auto = self._stage_auto(policy, "script", default=True)
        trends_scanned = self.maybe_scan_trends(policy)
        queue_expired = self.expire_queue(policy)
        created = self.generate_scripts() if started_auto else 0
        approved = 0
        scheduled = 0
        if self._stage_auto(policy, "approve"):
            approved = self.approve_offers(policy or {})
        if self._stage_auto(policy, "schedule"):
            scheduled = self.schedule_approved(policy or {})

        report = self.readiness()
        report["trends_scanned"] = trends_scanned
        report["queue_expired"] = queue_expired
        report["scripts_created"] = created
        report["offers_auto_approved"] = approved
        report["posts_auto_scheduled"] = scheduled
        report["automation_mode"] = (policy or {}).get("mode", "legacy")
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
    hb = WorkerHeartbeat(args.api, "batch")
    if args.once:
        hb.beat("ok", detail="one-shot batch")
        try:
            batch.run_once()
        finally:
            hb.beat("stopped", detail="one-shot batch complete")
        return
    hb.start()
    try:
        batch.run_forever(args.interval)
    finally:
        hb.stop()


if __name__ == "__main__":
    main()
