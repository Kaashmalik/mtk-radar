"""Public-page capture worker — screenshots for storyboard `page` scenes.

Distinct from the guided capture (main.py), which is a HUMAN-operated
recording of a real claim flow. This worker only photographs PUBLIC pages a
reviewer asked for (Studio → Storyboard → Capture pages), so explainers can
show the actual source instead of only quoting it.

Safety posture (each step fails closed):
- the URL must pass the shared egress policy (https, port 443, no
  credentials) and its host must resolve to PUBLIC addresses only;
- robots.txt is honoured for our user agent (5xx/unreachable robots = no);
- a fresh, cookie-less, storage-less headless browser context per page —
  never a logged-in profile — with downloads and service workers blocked;
- ALL browser traffic goes through a loopback CONNECT proxy
  (egress_proxy.py) that resolves every host itself, requires public
  addresses and connects to exactly the validated address — redirect hops,
  iframes, sub-resources and DNS rebinding cannot reach private networks;
  the route check and the final-URL check remain as defence in depth;
- bounded timeouts; a viewport-sized 1920x1080 PNG (no full-page scroll
  dumps); results are reported per URL as ok / failed / refused.

Run:  python workers/capture/page_capture.py --watch     (job queue)
      python workers/capture/page_capture.py --url https://… --out shot.png
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))

from object_storage import make_from_env, page_capture_key  # noqa: E402
from source_adapters.egress import (  # noqa: E402
    EgressError,
    EgressPolicy,
    _default_resolver,
    _resolve_public,
    safe_fetch,
    validate_url,
)
from worker_heartbeat import WorkerHeartbeat, lease_holder  # noqa: E402

from egress_proxy import EgressProxy  # noqa: E402

log = logging.getLogger("page_capture")

USER_AGENT_TOKEN = "MTK-Radar-PageCapture"
USER_AGENT = (f"Mozilla/5.0 (compatible; {USER_AGENT_TOKEN}/1.0; "
              "+https://github.com/Kaashmalik/mtk-radar)")
NAV_TIMEOUT_MS = 30_000
SETTLE_TIMEOUT_MS = 8_000
VIEWPORT = {"width": 1920, "height": 1080}


class Refused(Exception):
    """The page must not be captured (policy), as opposed to a failure."""


# ------------------------------------------------------------------- policy

@dataclass
class HostGuard:
    """Decides per request whether its host is public (cached per host)."""

    resolver: Callable[[str, int], list[str]] = _default_resolver
    allow_private: bool = False
    _cache: dict[str, bool] = field(default_factory=dict)

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        scheme = (parts.scheme or "").lower()
        if scheme in ("data", "blob", "about"):
            return True  # in-page resources, no network
        if scheme not in ("http", "https"):
            return False
        host = (parts.hostname or "").lower()
        if not host:
            return False
        if host not in self._cache:
            try:
                _resolve_public(host, parts.port or (443 if scheme == "https" else 80),
                                self.resolver, allow_private=self.allow_private)
                self._cache[host] = True
            except EgressError:
                self._cache[host] = False
        return self._cache[host]


def robots_allows(robots_text: Optional[str], url: str, status: Optional[int]) -> bool:
    """RFC 9309 semantics: 4xx = no rules (allowed); 5xx/unreachable = disallow."""
    if status is None or status >= 500:
        return False
    if status >= 400 or not robots_text:
        return True
    parser = RobotFileParser()
    parser.parse(robots_text.splitlines())
    return parser.can_fetch(USER_AGENT_TOKEN, url)


def robots_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


def check_robots(url: str, policy: EgressPolicy, fetch=safe_fetch) -> bool:
    try:
        result = fetch(robots_url(url), policy=policy,
                       headers={"User-Agent": USER_AGENT})
    except EgressError:
        return False
    except Exception:  # noqa: BLE001 — unreachable robots = disallow
        return False
    text = result.body.decode("utf-8", errors="replace") if result.status < 400 else None
    return robots_allows(text, url, result.status)


def preflight(url: str, policy: EgressPolicy, guard: HostGuard,
              fetch=safe_fetch) -> None:
    """Raise Refused when the URL may not be captured at all."""
    try:
        validate_url(url, policy)
    except EgressError as exc:
        raise Refused(str(exc)) from None
    if not guard.allows(url):
        raise Refused("host does not resolve to public addresses only")
    if not check_robots(url, policy, fetch):
        raise Refused("robots.txt disallows (or could not be read for) this page")


# ------------------------------------------------------------------ capture

@dataclass
class Shot:
    final_url: str
    title: str
    http_status: Optional[int]
    png: bytes


def capture(url: str, guard: HostGuard, *, playwright_factory=None,
            proxy_factory=None) -> Shot:
    """Load one public page in a fresh sandboxed context and screenshot it."""
    if playwright_factory is None:
        from playwright.sync_api import sync_playwright
        playwright_factory = sync_playwright
    if proxy_factory is None:
        proxy_factory = lambda: EgressProxy(guard.resolver,  # noqa: E731
                                            allow_private=guard.allow_private)
    blocked: list[str] = []

    def route(route_obj):
        request_url = route_obj.request.url
        if guard.allows(request_url):
            route_obj.continue_()
        else:
            blocked.append(urlsplit(request_url).hostname or "?")
            route_obj.abort()

    with proxy_factory() as proxy, playwright_factory() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy={"server": proxy.url},
            # Without this Chromium bypasses the proxy for localhost.
            args=["--disable-gpu", "--proxy-bypass-list=<-loopback>"],
        )
        try:
            context = browser.new_context(
                viewport=VIEWPORT, device_scale_factor=1, user_agent=USER_AGENT,
                accept_downloads=False, service_workers="block",
                java_script_enabled=True, locale="en-US",
            )
            context.route("**/*", route)
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
            except Exception:  # noqa: BLE001 — busy pages: capture what loaded
                pass
            final_url = page.url
            if not guard.allows(final_url):
                raise Refused("page redirected to a non-public host")
            png = page.screenshot(type="png", full_page=False)
            title = (page.title() or "")[:300]
            status = response.status if response is not None else None
            context.close()
        finally:
            browser.close()
        refused = getattr(proxy, "refused", [])
    if blocked or refused:
        log.warning("blocked %d request(s) to non-public hosts: %s",
                    len(blocked) + len(refused),
                    ", ".join(sorted(set(blocked) | set(refused))[:5]))
    return Shot(final_url, title, status, png)


# ----------------------------------------------------------------- job loop

class Worker:
    def __init__(self, api_url: str, out_dir: Path, *, token: str = "",
                 guard: Optional[HostGuard] = None, capture_fn=capture,
                 fetch=safe_fetch):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.api = httpx.Client(base_url=api_url.rstrip("/"), timeout=30, headers=headers)
        self.out_dir = Path(out_dir)
        self.policy = EgressPolicy()
        self.guard = guard or HostGuard()
        self.capture_fn = capture_fn
        self.fetch = fetch
        self.holder = lease_holder("page-capture")

    def _report(self, capture_id: str, **body) -> bool:
        """True only when the API recorded the outcome (2xx, or 409 =
        already recorded by an earlier attempt)."""
        try:
            resp = self.api.post(f"/page-captures/{capture_id}/result", json=body)
        except httpx.HTTPError as exc:
            log.error("could not report page capture %s: %s", capture_id, exc)
            return False
        if 200 <= resp.status_code < 300 or resp.status_code == 409:
            return True
        log.error("page capture %s result refused: HTTP %s", capture_id, resp.status_code)
        return False

    def process(self, offer_id: str, capture_id: str, url: str) -> tuple[str, bool]:
        """(outcome, recorded). Never raises: one page never stops the batch."""
        try:
            preflight(url, self.policy, self.guard, self.fetch)
            shot = self.capture_fn(url, self.guard)
        except Refused as exc:
            return "refused", self._report(capture_id, status="refused",
                                           detail=str(exc)[:900])
        except Exception as exc:  # noqa: BLE001
            return "failed", self._report(capture_id, status="failed",
                                          detail=f"{type(exc).__name__}: {exc}"[:900])
        try:
            storage = make_from_env()
            if storage is None:
                # The API serves screenshots only from managed storage, and the
                # render worker may run on another host: a local path is useless.
                raise RuntimeError("object storage is not configured — set "
                                   "MTK_STORAGE_BACKEND on the page-capture worker")
            local = self.out_dir / offer_id / f"{capture_id}.png"
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(shot.png)
            digest = hashlib.sha256(shot.png).hexdigest()
            ref = storage.put(local, page_capture_key(offer_id, capture_id))
        except Exception as exc:  # noqa: BLE001 — storage outage: report, retry later
            return "failed", self._report(capture_id, status="failed",
                                          detail=f"storing the screenshot failed: {exc}"[:900])
        return "ok", self._report(capture_id, status="ok", final_url=shot.final_url[:2000],
                                  title=(shot.title or "")[:300] or None, image_ref=ref,
                                  image_sha256=digest, http_status=shot.http_status)

    def _job_result(self, job_id: str, *, ok: bool, detail: str) -> None:
        body = {"ok": ok, "worker": self.holder, "detail": detail[:1900]}
        if not ok:
            body["retry_after_s"] = 120
        try:
            self.api.post(f"/jobs/{job_id}/result", json=body)
        except httpx.HTTPError as exc:
            log.error("could not settle page-capture job %s: %s", job_id, exc)

    def drain(self, limit: int = 20) -> int:
        """Claim and run page_capture jobs. Never raises on API/storage
        trouble: an unsettled job would keep its lease and stall captures."""
        done = 0
        for _ in range(limit):
            try:
                resp = self.api.post("/jobs/claim", json={
                    "worker": self.holder, "lease_s": 900, "kinds": ["page_capture"]})
                job = resp.json() if resp.status_code == 200 else {}
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("page-capture queue unavailable: %s", exc)
                return done
            if not job.get("claimed"):
                return done
            try:
                offer_id = str(job.get("entity_id"))
                wanted = set((job.get("payload") or {}).get("capture_ids") or [])
                rows = self.api.get(f"/offers/{offer_id}/page-captures").json()
                results = [self.process(offer_id, r["id"], r["url"])
                           for r in rows if r["id"] in wanted and r["status"] == "requested"]
            except Exception as exc:  # noqa: BLE001
                log.exception("page-capture job %s failed", job.get("id"))
                self._job_result(job["id"], ok=False, detail=f"job failed: {exc}")
                continue
            unrecorded = [outcome for outcome, recorded in results if not recorded]
            summary = ", ".join(outcome for outcome, _ in results) or "nothing pending"
            if unrecorded:
                # The capture rows are still "requested": retry so the result
                # is delivered instead of the job pretending to succeed.
                self._job_result(job["id"], ok=False,
                                 detail=f"{len(unrecorded)} result(s) not recorded: {summary}")
            else:
                self._job_result(job["id"], ok=True, detail=f"page captures: {summary}")
            done += 1
        return done


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    parser = argparse.ArgumentParser(description="MTK RADAR public-page capture")
    parser.add_argument("--api", default=os.environ.get("MTK_API_URL")
                        or os.environ.get("API_URL") or "http://localhost:8000")
    parser.add_argument("--out", default="./page-captures")
    parser.add_argument("--watch", action="store_true", help="drain the job queue forever")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--url", help="capture one URL locally (no API), for testing")
    args = parser.parse_args()
    if args.url:
        guard, policy = HostGuard(), EgressPolicy()
        preflight(args.url, policy, guard)
        shot = capture(args.url, guard)
        Path(args.out).write_bytes(shot.png)
        print(f"saved {args.out} — {shot.title} ({shot.final_url})")
        return
    token = (os.environ.get("MTK_WORKER_TOKEN") or os.environ.get("MTK_API_TOKEN") or "").strip()
    worker = Worker(args.api, Path(args.out), token=token)
    heartbeat = WorkerHeartbeat(args.api, "page-capture", interval_s=60) if args.watch else None
    if heartbeat:
        heartbeat.start()
    try:
        while True:
            try:
                worker.drain()
            except Exception:  # noqa: BLE001 — the watch loop must survive anything
                log.exception("page-capture sweep crashed; retrying next interval")
            if not args.watch:
                return
            time.sleep(max(10, args.interval))
    finally:
        if heartbeat:
            heartbeat.stop()


if __name__ == "__main__":
    main()
