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
- EVERY request the page makes is checked: requests to hosts that resolve
  to loopback/private/link-local addresses are aborted (no SSRF via
  embedded resources or redirects), and the final URL is re-validated;
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
from worker_heartbeat import lease_holder  # noqa: E402

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


def capture(url: str, guard: HostGuard, *, playwright_factory=None) -> Shot:
    """Load one public page in a fresh sandboxed context and screenshot it."""
    if playwright_factory is None:
        from playwright.sync_api import sync_playwright
        playwright_factory = sync_playwright
    blocked: list[str] = []

    def route(route_obj):
        request_url = route_obj.request.url
        if guard.allows(request_url):
            route_obj.continue_()
        else:
            blocked.append(urlsplit(request_url).hostname or "?")
            route_obj.abort()

    with playwright_factory() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-gpu"])
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
    if blocked:
        log.warning("blocked %d request(s) to non-public hosts: %s",
                    len(blocked), ", ".join(sorted(set(blocked))[:5]))
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

    def _report(self, capture_id: str, **body) -> None:
        try:
            self.api.post(f"/page-captures/{capture_id}/result", json=body)
        except httpx.HTTPError as exc:
            log.error("could not report page capture %s: %s", capture_id, exc)

    def process(self, offer_id: str, capture_id: str, url: str) -> str:
        try:
            preflight(url, self.policy, self.guard, self.fetch)
            shot = self.capture_fn(url, self.guard)
        except Refused as exc:
            self._report(capture_id, status="refused", detail=str(exc)[:900])
            return "refused"
        except Exception as exc:  # noqa: BLE001 — one page never stops the batch
            self._report(capture_id, status="failed",
                         detail=f"{type(exc).__name__}: {exc}"[:900])
            return "failed"
        local = self.out_dir / offer_id / f"{capture_id}.png"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(shot.png)
        digest = hashlib.sha256(shot.png).hexdigest()
        storage = make_from_env()
        ref = storage.put(local, page_capture_key(offer_id, capture_id)) if storage else str(local)
        self._report(capture_id, status="ok", final_url=shot.final_url[:2000],
                     title=shot.title or None, image_ref=ref, image_sha256=digest,
                     http_status=shot.http_status)
        return "ok"

    def drain(self, limit: int = 20) -> int:
        done = 0
        for _ in range(limit):
            resp = self.api.post("/jobs/claim", json={
                "worker": self.holder, "lease_s": 900, "kinds": ["page_capture"]})
            if resp.status_code != 200 or not resp.json().get("claimed"):
                return done
            job = resp.json()
            offer_id = str(job.get("entity_id"))
            wanted = set((job.get("payload") or {}).get("capture_ids") or [])
            rows = self.api.get(f"/offers/{offer_id}/page-captures").json()
            outcomes = [self.process(offer_id, r["id"], r["url"])
                        for r in rows if r["id"] in wanted and r["status"] == "requested"]
            self.api.post(f"/jobs/{job['id']}/result", json={
                "ok": True, "worker": self.holder,
                "detail": f"page captures: {', '.join(outcomes) or 'nothing pending'}"[:1900]})
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
    while True:
        worker.drain()
        if not args.watch:
            return
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    main()
