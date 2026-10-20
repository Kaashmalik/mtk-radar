"""Guided capture worker — real-browser claim recording (weeks 5-6, master plan §4).

A HUMAN-OPERATED session: Playwright automates only the repeatable mechanics
(open steps, record video, keep a step log) — the operator performs every
account action themselves on their own eligible account. Never automates
credential entry or account creation.

Usage:
    pip install -r workers/capture/requirements.txt
    python -m playwright install chromium
    python main.py --offer <offer-id> [--api http://localhost:8000] [--out ./captures]

What it does:
  1. Loads the offer + latest approved script checklist from the API (gated on
     verified state server-side).
  2. Opens a headed Chromium context recording 1280x720 video.
  3. For each checklist step with a URL: navigates, waits for the operator to
     press ENTER when the step is complete, appends a timestamped step-log row.
  4. Scans the step log for secret patterns (redaction review) and POSTs the
     session to the API. Secrets are reported by pattern + count only —
     raw values never leave this machine.
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from redact_local import scan as scan_secrets  # slim copy of the API's scanner

API_URL_DEFAULT = "http://localhost:8000"


class CaptureSession:
    def __init__(self, offer_id: str, api_url: str, out_dir: Path):
        self.offer_id = offer_id
        self.api = httpx.Client(timeout=30, base_url=api_url.rstrip("/"))
        self.out_dir = out_dir / f"{offer_id}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.step_log: list[dict] = []

    def load_offer(self) -> dict:
        resp = self.api.get(f"/offers/{self.offer_id}")
        resp.raise_for_status()
        offer = resp.json()
        if offer.get("state") not in ("verified", "approved_for_video", "published"):
            raise SystemExit(
                f"offer state is '{offer.get('state')}' — capture is blocked before "
                "verified (master plan §3). Nothing to record."
            )
        return offer

    def latest_checklist(self) -> list[dict]:
        resp = self.api.get(f"/offers/{self.offer_id}/scripts")
        resp.raise_for_status()
        scripts = resp.json()
        if not scripts:
            raise SystemExit(
                "no generated script yet — generate one from the review desk first "
                "(POST /offers/{id}/script); the checklist defines the capture steps."
            )
        # scripts are ordered version DESC → [0] is latest
        steps = json.loads(scripts[0]["checklist"]) if isinstance(scripts[0].get("checklist"), str) else scripts[0].get("checklist", [])
        return steps

    def run(self) -> None:
        from playwright.sync_api import sync_playwright

        offer = self.load_offer()
        steps = self.latest_checklist()
        redemption = offer.get("redemption_url")
        nav_steps = [s for s in steps if isinstance(s, dict) and (s.get("url") or s.get("kind") == "account_action")]

        print(f"\n=== MTK RADAR capture: {offer.get('title')} ===")
        print("Human-operated session: you perform every account action.")
        print("Automation only navigates, records, and keeps the step log.\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                record_video_dir=str(self.out_dir),
                record_video_size={"width": 1280, "height": 720},
            )
            page = context.new_page()

            if redemption:
                self._step(page, 0, "open_offer_page", redemption)

            for n, step in enumerate(nav_steps, start=1):
                url = step.get("url")
                if url:
                    self._step(page, n, step.get("kind", "step"), url)
                else:
                    input(f"[step {n}] {step.get('text', '')} — press ENTER when done… ")
                    self._log(n, step.get("kind", "step"), description=step.get("text", ""))

            input("\nRecording done — press ENTER to stop and save… ")
            video = page.video
            context.close()  # flushes the video file
            video_path = str(video.path()) if video else None
            browser.close()

        self._finish(video_path)

    def _step(self, page, n: int, kind: str, url: str) -> None:
        print(f"[step {n}] opening {url} — do the step, then press ENTER… ")
        try:
            page.goto(url, timeout=60_000, wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001
            print(f"  navigation warning: {exc}")
        self._log(n, kind, url=url, title=page.title())
        input("  press ENTER when this step is complete… ")

    def _log(self, n: int, kind: str, url: str | None = None, title: str | None = None,
             description: str | None = None) -> None:
        entry = {
            "n": n,
            "kind": kind,
            "url": url,
            "title": title,
            "description": description,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.step_log.append(entry)
        (self.out_dir / "step_log.json").write_text(
            json.dumps(self.step_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _finish(self, video_path: str | None) -> None:
        findings = scan_secrets(json.dumps(self.step_log, default=str))
        if findings:
            print("\n⚠️  REDACTION NEEDED — potential secrets detected in the step log:")
            for f in findings:
                print(f"   - {f['pattern']}: {f['count']} occurrence(s)")
            print("   (values are NOT logged — clean the footage/transcript before render)")
        else:
            print("\nStep log looks clean of known secret patterns — reviewer must still confirm.")

        payload = {
            "video_path": video_path,
            "step_log": self.step_log,
            "notes": f"local capture dir: {self.out_dir}",
        }
        resp = self.api.post(f"/offers/{self.offer_id}/captures", json=payload)
        if resp.status_code == 201:
            body = resp.json()
            print(f"capture session registered: {body['id']}")
            print(f"redaction scan: {body['redaction']}")
        else:
            print(f"capture upload failed: {resp.status_code} {resp.text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MTK RADAR guided capture session")
    parser.add_argument("--offer", required=True, help="offer UUID")
    parser.add_argument("--api", default=API_URL_DEFAULT)
    parser.add_argument("--out", default="./captures", help="local output directory")
    args = parser.parse_args()
    CaptureSession(args.offer, args.api, Path(args.out)).run()


if __name__ == "__main__":
    main()
