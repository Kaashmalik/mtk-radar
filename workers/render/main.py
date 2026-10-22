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
import covers as covers_mod  # noqa: E402
import motion as motion_mod  # noqa: E402
import narration as narration_mod  # noqa: E402
import project as project_mod  # noqa: E402
import render as render_mod  # noqa: E402
from object_storage import (  # noqa: E402
    captions_key,
    cover_key,
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
    def __init__(self, offer_id: str, api_url: str, out_root: Path,
                 language: str = "en", motion_template: str = "studio"):
        self.offer_id = offer_id
        self.api = httpx.Client(timeout=60, base_url=api_url.rstrip("/"), headers=_api_auth_headers())
        self.project = project_mod.project_dir(out_root, offer_id)
        self.script_version: int | None = None
        self.capture_id: str | None = None
        self.language = language
        self.motion_template = motion_template
        self.script_metadata: dict = {}
        self.language_policy: dict = {}
        self.caption_language = "en"
        self.copy_language = "en"

    # ---------------------------------------------------------------- fetch

    def _get(self, path: str, **kwargs):
        resp = self.api.get(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def load_sources(self, capture_id: str | None, language: str | None = None) -> dict:
        language = language or self.language
        offer = self._get(f"/offers/{self.offer_id}")
        if offer.get("state") not in VIDEO_STATES:
            raise SystemExit(
                f"offer state is '{offer.get('state')}' — render blocked before verified (§3)"
            )

        scripts = self._get(f"/offers/{self.offer_id}/scripts")
        if not scripts:
            raise SystemExit("no generated script — run the script step first")
        matching = [s for s in scripts if (s.get("language") or "en") == language]
        if not matching:
            if language != "en":
                raise SystemExit(
                    f"no {language} script — run Content Studio generation for this language first"
                )
            matching = [s for s in scripts if (s.get("language") or "en") == "en"]
        if not matching:
            raise SystemExit(
                f"no {language} script — generate this language before rendering"
            )
        latest = matching[0]
        self.script_version = latest["version"]
        self.script_language = language
        self.script_metadata = {}
        raw_metadata = latest.get("metadata")
        if raw_metadata:
            try:
                self.script_metadata = (json.loads(raw_metadata)
                                        if isinstance(raw_metadata, str) else raw_metadata)
            except (TypeError, ValueError):
                self.script_metadata = {}
        # §17 pin: hash of the exact markdown this render is produced from —
        # carried into the render row so publishing can verify render ↔ approval.
        self.script_version_hash = latest.get("version_hash")
        project_mod.write_script(self.project, latest["markdown"], latest["version"],
                                 language=language)

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

    def _load_language_policy(self) -> dict:
        """English-first defaults, fetched once per render job.

        The API is the source of truth; a missing/unreachable setting still
        falls back to English metadata + English captions and English-only
        narration, which is the safe default requested by the operator.
        """
        if self.language_policy:
            return self.language_policy
        policy = {
            "metadata_language": "en",
            "captions_language": "en",
            "narration_languages": ["en"],
            "default_narration_language": "en",
        }
        try:
            stored = self._get("/settings/language_policy")
            value = stored.get("value") if isinstance(stored, dict) else None
            if isinstance(value, dict):
                policy.update(value)
        except Exception:  # noqa: BLE001 — policy fetch must not block a safe render
            pass
        policy["metadata_language"] = policy.get("metadata_language") or "en"
        policy["captions_language"] = policy.get("captions_language") or "en"
        allowed = [str(lang) for lang in (policy.get("narration_languages") or ["en"])]
        policy["narration_languages"] = allowed or ["en"]
        self.language_policy = policy
        self.caption_language = policy["captions_language"]
        self.copy_language = policy["metadata_language"]
        return policy

    def _website_url(self, offer: dict) -> str:
        """Brand website for the cover/CTA, falling back to the offer URL."""
        try:
            brand = self._get("/settings/brand")
            value = brand.get("value") if isinstance(brand, dict) else None
            if isinstance(value, dict) and value.get("website_url"):
                return str(value["website_url"])
        except Exception:  # noqa: BLE001 — branding is optional, never fatal
            pass
        return str(offer.get("redemption_url") or "")

    def run(self, capture_video: str | None, preset_keys: list[str],
            skip_narration: bool, capture_id: str | None = None,
            languages: tuple[str, ...] | None = None) -> None:
        """Render one or more language versions of the same capture.

        English remains the default. Urdu (and any later language) reuses the
        exact capture + step log, but gets its own script, captions, narration
        and registered render row so approval/publishing can bind to the exact
        language hash.
        """
        policy = self._load_language_policy()
        allowed = tuple(policy["narration_languages"])
        requested = tuple(languages or (self.language,))
        render_languages = tuple(lang for lang in requested if lang in allowed)
        blocked = [lang for lang in requested if lang not in allowed]
        if blocked:
            log.warning(
                "voiceover disabled in Settings → Language policy, skipping: %s",
                ", ".join(blocked),
            )
        if not render_languages:
            raise SystemExit(
                "no allowed voiceover language — enable the language in "
                "Settings → Language policy first"
            )
        for language in render_languages:
            self.language = language
            self._run_language(capture_video, preset_keys, skip_narration,
                               capture_id, language)

    def _run_language(self, capture_video: str | None, preset_keys: list[str],
                      skip_narration: bool, capture_id: str | None,
                      language: str) -> None:
        sources = self.load_sources(capture_id, language)
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

        # captions from the step log (source-derived, deterministic) and the
        # real step timestamps, not a synthetic words-per-minute timeline.
        step_log = json.loads(capture["step_log"]) if capture and isinstance(capture.get("step_log"), str) \
            else (capture or {}).get("step_log") or []
        segments = captions_mod.segments_from_step_log(step_log) or [
            {"text": offer.get("title", "offer walkthrough")}
        ]
        cues = captions_mod.build_cues(segments)
        srt_path, vtt_path = project_mod.write_captions(
            self.project,
            captions_mod.to_srt(cues),
            captions_mod.to_vtt(cues),
            language=language,
            # English-first on-screen captions even for an Urdu voiceover.
            ass=captions_mod.to_ass(cues, language=self.caption_language),
        )
        caption_suffix = "" if language == "en" else f".{language}"
        captions_rel = f"assets/captions{caption_suffix}.ass"

        # optional TTS narration — synthetic narration must be disclosed (§5)
        narration_file, narration_used = None, False
        if not skip_narration:
            narration_dir = self.project / "assets" / "narration" / language
            narration = narration_mod.synthesize_all(
                narration_mod.narration_segments(sources["script"]["markdown"]),
                narration_dir,
                language=language,
            )
            if narration["used"]:
                # v0.14: mix per-segment files into ONE track and USE it in the
                # renders. A failed mix downgrades to capture audio — disclosure
                # metadata must never claim narration that is not in the video.
                track = narration_mod.mix_segments(narration["paths"], narration_dir)
                if track is not None:
                    narration_file = os.path.relpath(track, self.project)
            narration_used = narration_file is not None

        # deterministic cover source (SVG always; optional PNG when Pillow exists)
        website = self._website_url(offer)
        cover_bundle = covers_mod.generate_covers(
            self.project, offer,
            # Cover title/CTA stay in the configured package language (English
            # by default) even when this render's voiceover is Urdu.
            language=self.copy_language,
            website_url=website,
        )
        primary_cover = cover_bundle.get("primary") or {}
        cover_rel = primary_cover.get("png") or primary_cover.get("svg") or ""
        cover_path = f"projects/{self.offer_id}/{cover_rel}" if cover_rel else None

        # render every requested preset relative to the project dir
        video_rel = os.path.relpath(capture_video, self.project)
        capture_duration = render_mod.probe_duration(capture_video)
        results = []
        for key in preset_keys:
            preset = get_preset(key)
            language_suffix = "" if language == "en" else f"-{language}"
            output = f"renders/{offer['id']}-{preset.key}{language_suffix}.mp4"
            motion_filter = motion_mod.build_motion_filter(
                preset,
                title=offer.get("title", ""),
                provider=offer.get("provider", ""),
                # On-screen lower-third copy follows the package language
                # (English by default), not the voiceover language.
                language=self.copy_language,
                duration_s=capture_duration,
                template=self.motion_template,
            )
            cmd = render_mod.build_ffmpeg_cmd(
                video_rel, output, preset,
                captions=captions_rel,
                narration=narration_file,  # mixed track maps 1:a + -shortest
                motion=motion_filter,
            )
            log.info("rendering %s/%s :: %s", language, preset.key,
                     render_mod.describe(cmd))
            proc = render_mod.run(cmd, self.project)
            if proc.returncode != 0:
                log.error("ffmpeg failed (%s/%s):\n%s", language, preset.key,
                          proc.stderr[-2000:])
                raise SystemExit(f"ffmpeg failed for preset {preset.key} ({language})")
            duration = render_mod.probe_duration(str(self.project / output))
            results.append({
                "preset": preset.key,
                "language": language,
                "width": preset.width,
                "height": preset.height,
                "video_path": f"projects/{self.offer_id}/{output}",
                "captions_path": f"projects/{self.offer_id}/assets/captions{caption_suffix}.srt",
                "cover_path": cover_path,
                "duration_s": duration,
                "command": render_mod.describe(cmd),
            })
            log.info("rendered %s/%s → %s", language, preset.key, output)

        manifest = project_mod.build_edit_manifest(
            offer=offer,
            script_version=self.script_version,
            capture_id=self.capture_id,
            capture_video=capture_video if isinstance(capture_video, str) else None,
            srt=str(srt_path), vtt=str(vtt_path),
            narration_used=narration_used,
            renders=results,
            language=language,
            covers=cover_bundle.get("covers", []),
            motion=motion_mod.motion_metadata(self.motion_template, language),
            captions_language=self.caption_language,
        )
        manifest_path = project_mod.write_edit_manifest(self.project, manifest,
                                                        language=language)
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
                        self.project / f"renders/{offer['id']}-{preset}{'' if language == 'en' else '-' + language}.mp4",
                        render_key(offer["id"], preset, language),
                    )
                    render_row["captions_path"] = storage.put(
                        self.project / f"assets/captions{'' if language == 'en' else '.' + language}.srt",
                        captions_key(offer["id"], preset, language),
                    )
                    if cover_rel:
                        ext = Path(cover_rel).suffix.lstrip(".") or "svg"
                        render_row["cover_path"] = storage.put(
                            self.project / cover_rel,
                            cover_key(offer["id"], preset, language, ext=ext),
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
                "cover_path": render_row["cover_path"],
                "language": language,
                "motion_template": self.motion_template,
                "script_version": self.script_version,
                "script_version_hash": self.script_version_hash,
                "capture_id": self.capture_id,
                "disclosure": narration_mod.disclosure_record(narration_used,
                                                              language=language),
                "metadata": {
                    "language": language,
                    "voiceover_language": language,
                    "copy_language": self.copy_language,
                    "captions_language": self.caption_language,
                    "beats": self.script_metadata.get("beats", []),
                    "motion": motion_mod.motion_metadata(self.motion_template, language),
                    "cover": primary_cover.get("spec", {}),
                },
            }
            resp = self.api.post(f"/offers/{self.offer_id}/renders", json=payload)
            if resp.status_code == 201:
                log.info("render registered: %s (%s/%s)", resp.json().get("id"),
                         language, render_row["preset"])
            else:
                log.error("render registration failed: %s %s", resp.status_code, resp.text)


def _load_policy(client: httpx.Client) -> dict | None:
    """Read the automation policy. None means unavailable/legacy → keep the
    existing auto-render behaviour (the API still gates every render)."""
    try:
        resp = client.get("/automation/policy")
        if getattr(resp, "status_code", 200) >= 300:
            return None
        body = resp.json()
        if not isinstance(body, dict):
            return None
        policy = body.get("policy")
        return policy if isinstance(policy, dict) else None
    except Exception:  # noqa: BLE001 — a render sweep must never die on policy I/O
        return None


def _render_stage_allowed(policy: dict | None) -> bool:
    if policy is None:
        return True
    if policy.get("paused") or policy.get("dry_run"):
        return False
    return (policy.get("stages") or {}).get("render") == "auto"


def sweep(api_url: str, out_root: Path, preset_keys: list[str],
          skip_narration: bool, limit: int = 10,
          motion_template: str = "studio") -> int:
    """Auto-render the ready queue (v0.19).

    The API's /render-candidates lists offers that have a script + a
    redaction-reviewed capture but no render for that exact script version.
    Each candidate is rendered through the SAME code path as a manual run
    (RenderJob.run) — so automation cannot produce a different artifact than
    an operator would. One bad candidate never stops the sweep.
    """
    client = httpx.Client(timeout=60, base_url=api_url.rstrip("/"),
                          headers=_api_auth_headers())
    policy = _load_policy(client)
    if not _render_stage_allowed(policy):
        state = "paused" if (policy or {}).get("paused") else (
            "dry-run" if (policy or {}).get("dry_run") else "human-controlled")
        log.info("render stage is %s in Settings — sweep skipped", state)
        return 0
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
        language = candidate.get("language") or "en"
        # Keep the v0.19 three-argument constructor shape for the default
        # English/studio case (fake jobs and older callers rely on it).
        job_kwargs = {}
        if language != "en":
            job_kwargs["language"] = language
        if motion_template != "studio":
            job_kwargs["motion_template"] = motion_template
        job = RenderJob(offer_id, api_url, out_root, **job_kwargs)
        try:
            kwargs = {
                "capture_video": None,
                "preset_keys": preset_keys,
                "skip_narration": skip_narration,
                "capture_id": candidate.get("capture_id"),
            }
            # Keep the v0.19 FakeJob-compatible call shape for English, while a
            # non-English candidate renders only its own language.
            if language != "en":
                kwargs["languages"] = (language,)
            job.run(**kwargs)
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
    parser.add_argument("--languages", default="en", help="comma list: en,ur (default en)")
    parser.add_argument("--motion", default="studio", choices=list(motion_mod.TEMPLATES),
                        help="branded motion template (none = legacy export)")
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
    languages = tuple(k.strip() for k in args.languages.split(",") if k.strip())
    for language in languages:
        if language not in ("en", "ur"):
            raise SystemExit(f"unknown language '{language}' — known: en, ur")

    if args.sweep:
        if not args.watch:
            sweep(args.api, Path(args.out), presets, args.skip_narration, args.limit,
                  args.motion)
            return
        while True:  # service mode: the render queue is self-serving
            sweep(args.api, Path(args.out), presets, args.skip_narration, args.limit,
                  args.motion)
            time.sleep(max(30, args.interval))
    if not args.offer:
        raise SystemExit("pass --offer <OFFER_ID> or --sweep")

    RenderJob(args.offer, args.api, Path(args.out),
              language=languages[0], motion_template=args.motion).run(
        capture_video=args.video,
        preset_keys=presets,
        skip_narration=args.skip_narration,
        capture_id=args.capture,
        languages=languages,
    )


if __name__ == "__main__":
    main()
