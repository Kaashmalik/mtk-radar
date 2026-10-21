"""Render worker — FFmpeg export pipeline (weeks 7-8, master plan §5/§18).

Rebuilds a full video project from versioned source assets:
  script.md (pinned version) + step log + capture video →
  captions (.srt/.vtt) + optional TTS narration + 16:9 / 9:16 exports +
  edit manifest — everything reproducible, never hand-edited.

Usage:
    pip install -r workers/render/requirements.txt    # ffmpeg must be on PATH
    python main.py --offer <OFFER_ID> [--capture <CAPTURE_ID>] \
        [--video path/to/capture.mp4] [--presets landscape,vertical] \
        [--api http://localhost:8000] [--out ./projects]

Gating enforced server-side:
- renders can only be registered for offers in video-allowed states AND
  whose capture passed redaction review.
"""

import argparse
import json
import logging
import os
import sys
import time
import shutil
from pathlib import Path

import httpx


_API_TOKEN = os.environ.get("MTK_API_TOKEN", "").strip()

def _api_auth_headers() -> dict:
    """Authorization headers for the API when MTK_API_TOKEN is configured
    (services/api/api_hardening.py). Empty dict = open local dev API."""
    return {"Authorization": f"Bearer {_API_TOKEN}"} if _API_TOKEN else {}
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))

import captions as captions_mod  # noqa: E402
import narration as narration_mod  # noqa: E402
import project as project_mod  # noqa: E402
import render as render_mod  # noqa: E402
from object_storage import (  # noqa: E402
    captions_key,
    make_from_env,
    materialize,
    render_key,
)
from presets import get_preset  # noqa: E402

API_URL_DEFAULT = "http://localhost:8000"
VIDEO_STATES = ("verified", "approved_for_video", "published")
# the same override the render/narration modules honour (FFMPEG_PATH=/path/to/ffmpeg)
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("render")


class RenderJob:
    def __init__(self, offer_id: str, api_url: str, out_root: Path):
        self.offer_id = offer_id
        self.api = httpx.Client(timeout=60, base_url=api_url.rstrip("/"), headers=_api_auth_headers())
        self.project = project_mod.project_dir(out_root, offer_id)
        self.script_version: int | None = None
        self.capture_id: str | None = None

    # ---------------------------------------------------------------- fetch

    def _get(self, path: str, **kwargs):
        resp = self.api.get(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def load_sources(self, capture_id: str | None) -> dict:
        offer = self._get(f"/offers/{self.offer_id}")
        if offer.get("state") not in VIDEO_STATES:
            raise SystemExit(
                f"offer state is '{offer.get('state')}' — render blocked before verified (§3)"
            )

        scripts = self._get(f"/offers/{self.offer_id}/scripts")
        if not scripts:
            raise SystemExit("no generated script — run the script step first")
        latest = scripts[0]
        self.script_version = latest["version"]
        # §17 pin: hash of the exact markdown this render is produced from —
        # carried into the render row so publishing can verify render ↔ approval.
        self.script_version_hash = latest.get("version_hash")
        project_mod.write_script(self.project, latest["markdown"], latest["version"])

        project_mod.write_evidence_json(self.project, offer.get("evidence", []))

        capture = None
        if capture_id:
            captures = self._get("/captures", params={"offer_id": self.offer_id})
            capture = next((c for c in captures if c["id"] == capture_id), None)
            if capture is None:
                raise SystemExit(f"capture {capture_id} not found for this offer")
            self.capture_id = capture_id
            project_mod.write_step_log(
                self.project,
                json.loads(capture["step_log"]) if isinstance(capture["step_log"], str)
                else (capture["step_log"] or []),
            )
        return {"offer": offer, "script": latest, "capture": capture}

    # --------------------------------------------------------------- render

    def run(self, capture_video: str | None, preset_keys: list[str],
            skip_narration: bool, capture_id: str | None = None) -> None:
        sources = self.load_sources(capture_id)
        offer = sources["offer"]
        capture = sources["capture"]

        if capture_video is None and capture:
            capture_video = capture.get("video_path")
        if not capture_video:
            raise SystemExit(
                "no capture video — pass --video or record one first "
                "(workers/capture/main.py)"
            )
        # v0.15: a managed ref (s3://, local://) is materialized into the
        # project first; plain paths keep working on the host that has them.
        if not isinstance(capture_video, str):  # defensive: asyncpg row value
            capture_video = str(capture_video)
        local_capture = materialize(
            capture_video, self.project / "assets" / "captures"
        )
        if local_capture is not None:
            capture_video = str(local_capture)
        elif not Path(capture_video).exists():
            raise SystemExit(
                f"capture video unavailable on this host: {capture_video} — "
                "configure MTK_STORAGE_* or pass --video with a local file"
            )

        # captions from the step log (source-derived, deterministic)
        step_log = json.loads(capture["step_log"]) if capture and isinstance(capture.get("step_log"), str) \
            else (capture or {}).get("step_log") or []
        segments = captions_mod.segments_from_step_log(step_log) or [
            {"text": offer.get("title", "offer walkthrough")}
        ]
        cues = captions_mod.build_cues(segments)
        srt_path, vtt_path = project_mod.write_captions(
            self.project, captions_mod.to_srt(cues), captions_mod.to_vtt(cues)
        )

        # optional TTS narration — synthetic narration must be disclosed (§5)
        narration_file, narration_used = None, False
        if not skip_narration:
            narration = narration_mod.synthesize_all(
                narration_mod.narration_segments(sources["script"]["markdown"]),
                self.project / "assets" / "narration",
            )
            if narration["used"]:
                # v0.14: mix per-segment files into ONE track and USE it in the
                # renders. A failed mix downgrades to capture audio — disclosure
                # metadata must never claim narration that is not in the video.
                track = narration_mod.mix_segments(
                    narration["paths"], self.project / "assets" / "narration"
                )
                if track is not None:
                    narration_file = os.path.relpath(track, self.project)
            narration_used = narration_file is not None

        # render every requested preset relative to the project dir
        video_rel = os.path.relpath(capture_video, self.project)
        results = []
        for key in preset_keys:
            preset = get_preset(key)
            output = f"renders/{offer['id']}-{preset.key}.mp4"
            cmd = render_mod.build_ffmpeg_cmd(
                video_rel, output, preset,
                captions="assets/captions.srt",
                narration=narration_file,  # mixed track maps 1:a + -shortest
            )
            log.info("rendering %s :: %s", preset.key, render_mod.describe(cmd))
            proc = render_mod.run(cmd, self.project)
            if proc.returncode != 0:
                log.error("ffmpeg failed (%s):\n%s", preset.key, proc.stderr[-2000:])
                raise SystemExit(f"ffmpeg failed for preset {preset.key}")
            duration = render_mod.probe_duration(str(self.project / output))
            results.append({
                "preset": preset.key,
                "width": preset.width,
                "height": preset.height,
                "video_path": f"projects/{self.offer_id}/{output}",
                "captions_path": f"projects/{self.offer_id}/assets/captions.srt",
                "duration_s": duration,
                "command": render_mod.describe(cmd),
            })
            log.info("rendered %s → %s", preset.key, output)

        manifest = project_mod.build_edit_manifest(
            offer=offer,
            script_version=self.script_version,
            capture_id=self.capture_id,
            capture_video=capture_video if isinstance(capture_video, str) else None,
            srt=str(srt_path), vtt=str(vtt_path),
            narration_used=narration_used,
            renders=results,
        )
        manifest_path = project_mod.write_edit_manifest(self.project, manifest)
        log.info("edit manifest written: %s", manifest_path)

        # v0.15: when storage is configured, outputs become managed refs
        # (s3://… or local://…) stored in the DB — consumers on any host can
        # materialize them. Unset MTK_STORAGE_BACKEND keeps the legacy
        # repo-relative paths (single-host flow).
        storage = make_from_env()
        if storage is not None:
            for render_row in results:
                preset = render_row["preset"]
                try:
                    render_row["video_path"] = storage.put(
                        self.project / f"renders/{offer['id']}-{preset}.mp4",
                        render_key(offer["id"], preset),
                    )
                    render_row["captions_path"] = storage.put(
                        self.project / "assets/captions.srt",
                        captions_key(offer["id"], preset),
                    )
                except OSError as exc:
                    log.error("storage upload failed (%s) — keeping local paths", exc)

        for render_row in results:
            payload = {
                "preset": render_row["preset"],
                "width": render_row["width"],
                "height": render_row["height"],
                "duration_s": render_row["duration_s"],
                "video_path": render_row["video_path"],
                "captions_path": render_row["captions_path"],
                "script_version": self.script_version,
                "script_version_hash": self.script_version_hash,
                "capture_id": self.capture_id,
                "disclosure": narration_mod.disclosure_record(narration_used),
            }
            resp = self.api.post(f"/offers/{self.offer_id}/renders", json=payload)
            if resp.status_code == 201:
                log.info("render registered: %s (%s)", resp.json().get("id"), render_row["preset"])
            else:
                log.error("render registration failed: %s %s", resp.status_code, resp.text)


def sweep(api_url: str, out_root: Path, preset_keys: list[str],
          skip_narration: bool, limit: int = 10) -> int:
    """Auto-render the ready queue (v0.19).

    The API's /render-candidates lists offers that have a script + a
    redaction-reviewed capture but no render for that exact script version.
    Each candidate is rendered through the SAME code path as a manual run
    (RenderJob.run) — so automation cannot produce a different artifact than
    an operator would. One bad candidate never stops the sweep.
    """
    client = httpx.Client(timeout=60, base_url=api_url.rstrip("/"),
                          headers=_api_auth_headers())
    try:
        candidates = client.get("/render-candidates", params={"limit": limit}).json()
    except httpx.HTTPError as exc:
        log.error("render sweep skipped (API unreachable): %s", exc)
        return 0

    rendered = 0
    for candidate in candidates:
        offer_id = candidate["offer_id"]
        log.info("render sweep: rendering offer %s (script v%s)", offer_id,
                 candidate.get("script_version"))
        job = RenderJob(offer_id, api_url, out_root)
        try:
            job.run(
                capture_video=None,
                preset_keys=preset_keys,
                skip_narration=skip_narration,
                capture_id=candidate.get("capture_id"),
            )
            rendered += 1
        except SystemExit as exc:
            log.error("render sweep: %s skipped — %s", offer_id, exc)
        except Exception as exc:  # noqa: BLE001 — one candidate never stops the sweep
            log.exception("render sweep: %s failed: %s", offer_id, exc)
    log.info("render sweep complete: %d/%d rendered", rendered, len(candidates))
    return rendered


def _require_ffmpeg() -> str:
    """Preflight: the ffmpeg binary this host will use. Honours FFMPEG_PATH
    (the same override the render/narration modules read) and names the binary
    it looked for, so a wrong PATH never hides the real knob."""
    if shutil.which(FFMPEG_PATH) is None:
        raise SystemExit(
            f"ffmpeg not found ('{FFMPEG_PATH}') — install it or set FFMPEG_PATH"
        )
    return FFMPEG_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="MTK RADAR render pipeline (FFmpeg)")
    parser.add_argument("--offer", default=None, help="render one offer (omit with --sweep)")
    parser.add_argument("--sweep", action="store_true",
                        help="render every ready candidate (script + reviewed capture)")
    parser.add_argument("--capture", default=None, help="capture session UUID (enables redaction gating)")
    parser.add_argument("--video", default=None, help="path to the capture video file")
    parser.add_argument("--presets", default="landscape,vertical", help="comma list: landscape,vertical")
    parser.add_argument("--api", default=API_URL_DEFAULT)
    parser.add_argument("--out", default="./projects")
    parser.add_argument("--skip-narration", action="store_true", help="never call TTS")
    parser.add_argument("--limit", type=int, default=10, help="max candidates per sweep")
    parser.add_argument("--watch", action="store_true",
                        help="keep sweeping every --interval seconds (service mode)")
    parser.add_argument("--interval", type=int, default=900, help="seconds between sweeps")
    args = parser.parse_args()

    _require_ffmpeg()

    presets = [k.strip() for k in args.presets.split(",") if k.strip()]

    if args.sweep:
        if not args.watch:
            sweep(args.api, Path(args.out), presets, args.skip_narration, args.limit)
            return
        while True:  # service mode: the render queue is self-serving
            sweep(args.api, Path(args.out), presets, args.skip_narration, args.limit)
            time.sleep(max(30, args.interval))
    if not args.offer:
        raise SystemExit("pass --offer <OFFER_ID> or --sweep")

    RenderJob(args.offer, args.api, Path(args.out)).run(
        capture_video=args.video,
        preset_keys=presets,
        skip_narration=args.skip_narration,
        capture_id=args.capture,
    )


if __name__ == "__main__":
    main()
