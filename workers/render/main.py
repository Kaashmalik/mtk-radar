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
import threading
import time
import uuid
import shutil
from pathlib import Path

import httpx


_API_TOKEN = (os.environ.get("MTK_WORKER_TOKEN")
              or os.environ.get("MTK_API_TOKEN") or "").strip()

def _api_auth_headers() -> dict:
    """Authorization headers for the API when MTK_API_TOKEN is configured
    (services/api/api_hardening.py). Empty dict = open local dev API."""
    return {"Authorization": f"Bearer {_API_TOKEN}"} if _API_TOKEN else {}
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))

from api_paging import iter_pages  # noqa: E402

import captions as captions_mod  # noqa: E402
import covers as covers_mod  # noqa: E402
import explainer as explainer_mod  # noqa: E402
import reframe as reframe_mod  # noqa: E402
import motion as motion_mod  # noqa: E402
import narration as narration_mod  # noqa: E402
import project as project_mod  # noqa: E402
import qc as qc_mod  # noqa: E402
import render as render_mod  # noqa: E402
from object_storage import (  # noqa: E402
    captions_key,
    cover_key,
    make_from_env,
    materialize,
    render_key,
)
from presets import get_preset  # noqa: E402
from worker_heartbeat import WorkerHeartbeat, lease_holder  # noqa: E402

API_URL_DEFAULT = "http://localhost:8000"
VIDEO_STATES = ("verified", "approved_for_video", "published")
# the same override the render/narration modules honour (FFMPEG_PATH=/path/to/ffmpeg)
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("render")


def _sha256(path: Path | None) -> str | None:
    """Digest of the exact asset bytes recorded in the render package pin."""
    if path is None:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_failure_row(
    *,
    preset,
    language: str,
    video_path: str,
    captions_path: str,
    cover_path: str | None,
    command: str,
    reason: str,
    stderr: str = "",
    expected_duration: float | None = None,
) -> dict:
    """A failed attempt is still a durable record, never a silent log line.

    It is registered with status=render_failed so the dead-letter view and
    metrics can show why the pipeline is stuck. Publishing and scheduling only
    accept status=rendered + qc_status=passed.
    """
    report = qc_mod.failure_report(
        stage="ffmpeg",
        errors=[reason],
        details={"stderr": (stderr or "")[-2000:]},
        preset=preset.key,
        expected_duration=expected_duration,
    )
    return {
        "preset": preset.key,
        "language": language,
        "width": preset.width,
        "height": preset.height,
        "video_path": video_path,
        "captions_path": captions_path,
        "cover_path": cover_path,
        "duration_s": None,
        # A failed attempt must never pin bytes that may be a stale previous
        # export or a partial file left by the encoder.
        "video_sha256": None,
        "captions_sha256": None,
        "cover_sha256": None,
        "command": command,
        "status": "render_failed",
        "qc_status": "failed",
        "qc_report": report,
    }


class RenderJob:
    def __init__(self, offer_id: str, api_url: str, out_root: Path,
                 language: str = "en", motion_template: str = "studio"):
        self.offer_id = offer_id
        self.api = httpx.Client(timeout=60, base_url=api_url.rstrip("/"), headers=_api_auth_headers())
        # Cost engine (WP-F): TTS cache + char budget + usage ledger.
        import sys as _sys
        _pkg = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "packages"))
        if _pkg not in _sys.path:
            _sys.path.insert(0, _pkg)
        import costing as _costing
        self.cost = _costing.CostClient(api_url)
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
            # Fetch the pinned capture by id. Scanning the first page of
            # /captures?offer_id=... reported a valid asset as missing once an
            # offer had more captures than one page.
            try:
                capture = self._get(f"/captures/{capture_id}")
            except Exception:  # noqa: BLE001 — normalized below
                capture = None
            if not capture or str(capture.get("id")) != str(capture_id):
                raise SystemExit(f"capture {capture_id} not found")
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

    def _explainer_brief(self) -> dict | None:
        """The current research brief when this offer is an explainer (M3)."""
        try:
            research = self._get(f"/offers/{self.offer_id}/research")
        except Exception:  # noqa: BLE001 — older API / unreachable: no explainer
            return None
        return explainer_mod.eligible_brief(research)

    def _storyboard_inputs(self) -> dict:
        """Saved storyboard + page captures from the API ({} on older APIs)."""
        try:
            board = self._get(f"/offers/{self.offer_id}/storyboard")
        except Exception:  # noqa: BLE001 — no storyboard API: suggested scenes
            return {}
        return board if isinstance(board, dict) else {}

    def _fetch_page_image(self, capture: dict) -> str | None:
        """Download a page screenshot via the API and verify its sha256."""
        import hashlib

        rel = f"assets/explainer/pages/{capture['id']}.png"
        try:
            resp = self.api.get(f"/page-captures/{capture['id']}/image")
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.warning("page capture %s unavailable: %s", capture["id"], exc)
            return None
        if hashlib.sha256(resp.content).hexdigest() != capture.get("image_sha256"):
            log.warning("page capture %s failed its sha256 check — scene dropped", capture["id"])
            return None
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        return rel

    def _build_explainer_base(self, offer: dict, brief: dict,
                              narration_s: float | None) -> tuple[str, list[dict]]:
        """Render the card base video + scene manifest into the project.

        Scenes come from the reviewer-saved storyboard when one exists
        (re-validated against TODAY's claim ledger), else the suggestion.
        Page scenes use verified screenshots; anything that cannot be drawn
        honestly is dropped before timing and listed in the manifest. The
        base runs slightly past the speech so the timeline preflight
        (capture must cover narration) holds without truncating anything.
        """
        sb = explainer_mod.storyboard
        total = (narration_s + 0.6) if narration_s else None
        board = self._storyboard_inputs()
        pages = [p for p in board.get("page_captures") or [] if p.get("status") == "ok"]
        current = board.get("current") or None
        dropped: list[str] = []
        if current:
            scenes, dropped = sb.validate(current.get("scenes") or [], brief, pages)
            version = current.get("version")
        else:
            scenes, version = sb.suggest(offer, brief, pages), None
        images: dict[str, str] = {}
        kept = []
        for scene in scenes:
            if scene["kind"] == "page" and scene.get("include", True):
                capture = next((p for p in pages if str(p["id"]) == scene["page_capture_id"]), None)
                rel = self._fetch_page_image(capture) if capture else None
                if rel is None:
                    dropped.append(f"page scene {scene['id']}: screenshot unavailable")
                    continue
                images[scene["id"]] = rel
            kept.append(scene)
        if dropped:
            log.warning("storyboard: %d scene(s) dropped: %s", len(dropped), "; ".join(dropped))
        scenes = sb.apply_timing(kept, total)
        if not scenes:
            raise RuntimeError("explainer has no drawable scenes — fix the storyboard")
        out_dir = self.project / "assets" / "explainer"
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest = explainer_mod.scene_manifest(self.offer_id, brief, scenes,
                                                storyboard_version=version, dropped=dropped)
        (out_dir / "scene_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        duration = scenes[-1]["end"]
        page_layers = [(images[s["id"]], s["start"], s["end"])
                       for s in scenes if s["id"] in images]
        # One base per orientation: the vertical export gets natively
        # composed 9:16 cards (see _video_for_preset), not a shrunken strip.
        for orientation, suffix in (("landscape", ""), ("vertical", "-vertical")):
            cards = f"assets/explainer/cards{suffix}.ass"
            (self.project / cards).write_text(
                explainer_mod.cards_ass(scenes, orientation), encoding="utf-8")
            cmd = explainer_mod.base_video_cmd(
                cards, f"assets/explainer/base{suffix}.mp4", duration, orientation,
                pages=page_layers)
            log.info("explainer %s base (%d scenes, storyboard %s, %.1fs, manifest %s) :: %s",
                     orientation, len(scenes), f"v{version}" if version else "suggested",
                     duration, manifest["sha256"][:12], render_mod.describe(cmd))
            proc = render_mod.run(cmd, self.project)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"explainer base render failed: {(proc.stderr or '')[-600:]}")
        return str(out_dir / "base.mp4"), scenes

    def _reframed_vertical(self, preset, capture_video: str):
        """The vertical preset with an activity-following crop, or unchanged."""
        import dataclasses

        crop = reframe_mod.crop_fraction()
        keys = reframe_mod.analyse(capture_video, crop)
        if not keys:
            log.info("vertical reframe: activity signal too weak — full-frame composition")
            return preset
        (self.project / "assets").mkdir(parents=True, exist_ok=True)
        (self.project / "assets" / "reframe-vertical.json").write_text(json.dumps({
            "crop_fraction": crop,
            "keyframes": [{"t": k.t, "center": k.center} for k in keys],
        }, indent=2), encoding="utf-8")
        log.info("vertical reframe: %d keyframes, crop %.0f%% of width", len(keys), crop * 100)
        return dataclasses.replace(
            preset, filter_chain=reframe_mod.vertical_focus_chain(keys, crop))

    def _video_for_preset(self, video_rel: str, preset_key: str) -> str:
        """The natively composed vertical explainer base when it exists."""
        if preset_key == "vertical" and video_rel.replace("\\", "/").endswith(
                "assets/explainer/base.mp4"):
            vertical = self.project / "assets" / "explainer" / "base-vertical.mp4"
            if vertical.exists():
                return os.path.relpath(vertical, self.project)
        return video_rel

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
        explainer_brief = None
        if not capture_video:
            # M3: a research EXPLAINER needs no hands-on capture — its base
            # video is built from the current brief after narration is known.
            # Every other track still requires a real recording.
            explainer_brief = self._explainer_brief()
            if explainer_brief is None:
                raise SystemExit(
                    "no capture video — pass --video or record one first "
                    "(workers/capture/main.py)"
                )
        if capture_video:
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

        # optional TTS narration — synthetic narration must be disclosed (§5).
        # Synthesize BEFORE captions so we can align cues to the actual spoken
        # segment durations instead of a words-per-minute estimate.
        narration_file, narration_used = None, False
        narration_texts: list[str] = []
        aligned_captions: list[dict] | None = None
        if not skip_narration:
            narration_dir = self.project / "assets" / "narration" / language
            narration_texts = narration_mod.narration_segments(
                sources["script"]["markdown"])
            narration = narration_mod.synthesize_all(
                narration_texts, narration_dir, language=language,
                cost=self.cost,
            )
            if narration["used"]:
                # v0.14: mix per-segment files into ONE track and USE it in the
                # renders. A failed mix downgrades to capture audio — disclosure
                # metadata must never claim narration that is not in the video.
                track = narration_mod.mix_segments(narration["paths"], narration_dir)
                if track is not None:
                    narration_file = os.path.relpath(track, self.project)
                narration_used = narration_file is not None
                # Speech-aligned captions only when the spoken language is the
                # on-screen caption language. A missing probe falls back safely
                # to the deterministic step-log timeline.
                if narration_used and language == self.caption_language:
                    cursor = 0.0
                    aligned: list[dict] = []
                    for text, audio_path in zip(narration_texts, narration["paths"]):
                        duration = render_mod.probe_duration(str(audio_path))
                        if not duration or duration <= 0:
                            aligned = []
                            break
                        aligned.append({"text": text, "start": cursor,
                                        "duration": duration})
                        cursor += duration
                    aligned_captions = aligned or None

        explainer_scenes: list[dict] = []
        if explainer_brief is not None:
            narration_s = (render_mod.probe_duration(str(self.project / narration_file))
                           if narration_file else None)
            capture_video, explainer_scenes = self._build_explainer_base(
                offer, explainer_brief, narration_s)

        # Captions from narration timing when available; otherwise from the
        # step log (source-derived, deterministic) with the real step
        # timestamps, not a synthetic words-per-minute timeline.
        if aligned_captions:
            segments = aligned_captions
        elif explainer_scenes:
            # No speech timing: caption each card for its on-screen time.
            segments = [{"text": f"{s['heading']}: {s.get('body', '')}".strip(": "),
                         "start": s["start"], "duration": s["end"] - s["start"]}
                        for s in explainer_scenes]
        else:
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

        # render every requested preset relative to the project dir
        video_rel = os.path.relpath(capture_video, self.project)
        capture_duration = render_mod.probe_duration(capture_video)
        narration_duration = (
            render_mod.probe_duration(str(self.project / narration_file))
            if narration_file else None
        )
        expected_duration, timeline_error = render_mod.resolve_timeline(
            capture_duration, narration_duration,
            narration_used=bool(narration_file),
        )
        timeline = {
            "basis": "speech" if narration_file else "capture",
            "capture_s": capture_duration,
            "narration_s": narration_duration if narration_file else None,
            "expected_s": expected_duration,
        }
        if timeline_error:
            log.error("timeline preflight failed (%s): %s", language, timeline_error)
        qc_config = qc_mod.QCConfig.from_env()
        qc_exempt_ranges = qc_mod.parse_exempt_ranges(
            self.script_metadata.get("qc_exempt_ranges")
        )
        results = []
        for key in preset_keys:
            preset = get_preset(key)
            if key == "vertical" and explainer_brief is None and reframe_mod.enabled():
                # V5: follow on-screen activity instead of shrinking the whole
                # 16:9 capture (falls back to full frame on a weak signal).
                preset = self._reframed_vertical(preset, capture_video)
            # Pair each delivery frame with the cover designed for it. A 16:9
            # thumbnail on a 9:16 Reel/TikTok is the wrong asset.
            selected_cover = covers_mod.cover_for_preset(cover_bundle, preset.key)
            cover_rel = selected_cover.get("png") or selected_cover.get("svg") or ""
            cover_path = f"projects/{self.offer_id}/{cover_rel}" if cover_rel else None
            language_suffix = "" if language == "en" else f"-{language}"
            output = f"renders/{offer['id']}-{preset.key}{language_suffix}.mp4"
            # Burn-in captions are frame-specific: the 9:16 preset must use a
            # 1080x1920 PlayRes and vertical margins, not a scaled 16:9 script.
            captions_rel = project_mod.write_preset_captions(
                self.project, cues, preset.key, preset.width, preset.height,
                language=language, caption_language=self.caption_language,
            )
            if timeline_error:
                results.append(_render_failure_row(
                    preset=preset, language=language,
                    video_path=f"projects/{self.offer_id}/{output}",
                    captions_path=f"projects/{self.offer_id}/assets/captions{caption_suffix}.srt",
                    cover_path=cover_path, command="",
                    reason=f"timeline preflight: {timeline_error}",
                    expected_duration=expected_duration,
                ))
                continue
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
                self._video_for_preset(video_rel, preset.key), output, preset,
                captions=captions_rel,
                narration=narration_file,  # mixed track maps 1:a
                motion=motion_filter,
                duration=expected_duration if narration_file else None,
                # Normalize to exactly what QC will measure, so a correct
                # render is not rejected for loudness it was never given.
                loudness=render_mod.Loudness(
                    target_lufs=qc_config.target_lufs,
                    max_true_peak=qc_config.max_true_peak,
                ),
            )
            log.info("rendering %s/%s :: %s", language, preset.key,
                     render_mod.describe(cmd))
            command = render_mod.describe(cmd)
            captions_local = self.project / f"assets/captions{caption_suffix}.srt"
            output_path = self.project / output
            try:
                proc = render_mod.run(cmd, self.project)
            except Exception as exc:  # noqa: BLE001 — persist the failed attempt
                log.error("ffmpeg invocation failed (%s/%s): %s", language,
                          preset.key, exc)
                results.append(_render_failure_row(
                    preset=preset, language=language,
                    video_path=f"projects/{self.offer_id}/{output}",
                    captions_path=f"projects/{self.offer_id}/assets/captions{caption_suffix}.srt",
                    cover_path=cover_path, command=command,
                    reason=f"ffmpeg invocation failed: {exc}",
                    expected_duration=expected_duration,
                ))
                continue
            if proc.returncode != 0:
                log.error("ffmpeg failed (%s/%s):\n%s", language, preset.key,
                          proc.stderr[-2000:])
                results.append(_render_failure_row(
                    preset=preset, language=language,
                    video_path=f"projects/{self.offer_id}/{output}",
                    captions_path=f"projects/{self.offer_id}/assets/captions{caption_suffix}.srt",
                    cover_path=cover_path, command=command,
                    reason=f"ffmpeg exited {proc.returncode} for preset {preset.key}",
                    stderr=proc.stderr or "",
                    expected_duration=expected_duration,
                ))
                continue

            duration = render_mod.probe_duration(str(output_path))
            qc_report = qc_mod.run(
                output_path,
                width=preset.width, height=preset.height, fps=preset.fps,
                preset=preset.key, expected_duration=expected_duration,
                captions_path=self.project / captions_rel,
                exempt_ranges=qc_exempt_ranges, config=qc_config,
            )
            qc_passed = qc_report.get("status") == "passed"
            results.append({
                "preset": preset.key,
                "language": language,
                "width": preset.width,
                "height": preset.height,
                "video_path": f"projects/{self.offer_id}/{output}",
                "captions_path": f"projects/{self.offer_id}/assets/captions{caption_suffix}.srt",
                "cover_path": cover_path,
                "duration_s": duration,
                "video_sha256": _sha256(output_path),
                "captions_sha256": _sha256(captions_local),
                "cover_sha256": _sha256(self.project / cover_rel) if cover_rel else None,
                "command": command,
                "status": "rendered" if qc_passed else "qc_failed",
                "qc_status": "passed" if qc_passed else "failed",
                "qc_report": qc_report,
            })
            if qc_passed:
                log.info("rendered %s/%s → %s (QC passed)", language, preset.key, output)
            else:
                log.error("QC failed %s/%s: %s", language, preset.key,
                          "; ".join(qc_report.get("errors") or ["unknown QC error"]))

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
            timeline=timeline,
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
            # A revision-scoped, attempt-unique prefix makes every uploaded
            # package immutable: a rerun can never overwrite bytes that were
            # already approved or published. Orphaned failed attempts are
            # cheap and can be garbage-collected by retention policy later.
            revision = (f"v{self.script_version}-"
                        f"{str(self.script_version_hash or 'unsigned')[:12]}")
            attempt = uuid.uuid4().hex[:12]
            for render_row in results:
                if render_row.get("status") != "rendered":
                    continue  # failed/QC-rejected media is never uploaded as an asset
                preset = render_row["preset"]
                # All three assets of one render are treated as a unit: if any
                # upload fails, the row reverts to its consistent local paths
                # (and their matching digests) — never a half-managed mix.
                original_paths = (render_row["video_path"],
                                  render_row["captions_path"],
                                  render_row["cover_path"])
                try:
                    render_row["video_path"] = storage.put(
                        self.project / f"renders/{offer['id']}-{preset}{'' if language == 'en' else '-' + language}.mp4",
                        render_key(offer["id"], preset, language,
                                   revision=revision, attempt=attempt),
                    )
                    render_row["captions_path"] = storage.put(
                        self.project / f"assets/captions{'' if language == 'en' else '.' + language}.srt",
                        captions_key(offer["id"], preset, language,
                                     revision=revision, attempt=attempt),
                    )
                    cover_ref = render_row.get("cover_path")
                    if cover_ref:
                        local_cover = self.project / str(cover_ref).removeprefix(
                            f"projects/{offer['id']}/"
                        )
                        ext = local_cover.suffix.lstrip(".") or "svg"
                        render_row["cover_path"] = storage.put(
                            local_cover,
                            cover_key(offer["id"], preset, language, ext=ext,
                                      revision=revision, attempt=attempt),
                        )
                except OSError as exc:
                    (render_row["video_path"], render_row["captions_path"],
                     render_row["cover_path"]) = original_paths
                    log.error("storage upload failed (%s) — row reverted to local "
                              "paths so path types and digests stay consistent", exc)

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
                "video_sha256": render_row.get("video_sha256"),
                "captions_sha256": render_row.get("captions_sha256"),
                "cover_sha256": render_row.get("cover_sha256"),
                "status": render_row.get("status", "rendered"),
                "qc_status": render_row.get("qc_status", "failed"),
                "qc_report": render_row.get("qc_report") or {},
                "capture_id": self.capture_id,
                "disclosure": narration_mod.disclosure_record(narration_used,
                                                              language=language),
                "metadata": {
                    "language": language,
                    "voiceover_language": language,
                    "copy_language": self.copy_language,
                    "captions_language": self.caption_language,
                    "beats": self.script_metadata.get("beats", []),
                    "timeline": timeline,
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

        failed = [row for row in results if row.get("status") != "rendered"]
        if failed:
            reasons = ", ".join(
                f"{row['preset']}:{(row.get('qc_report') or {}).get('stage', row.get('status'))}"
                for row in failed
            )
            raise SystemExit(
                f"{len(failed)} render attempt(s) failed for {language} ({reasons}) "
                "— see render dead-letter"
            )


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


def _render_candidate(api_url: str, out_root: Path, skip_narration: bool,
                      motion_template: str, candidate: dict,
                      preset_keys: list[str]) -> bool:
    """Render ONE candidate through the same code path as a manual run.

    Shared by the job-driven drain and the classic sweep so automation can
    never produce a different artifact depending on which path drove it.
    Returns False when the API reports no genuinely missing variant."""
    offer_id = candidate["offer_id"]
    # The API reports which variants are genuinely missing. Never re-render
    # a landscape export just because the vertical one is still absent.
    missing = [key for key in preset_keys
               if key in (candidate.get("missing_presets") or preset_keys)]
    if not missing:
        return False
    log.info("render sweep: rendering offer %s (script v%s, %s)", offer_id,
             candidate.get("script_version"), ", ".join(missing))
    language = candidate.get("language") or "en"
    # Keep the v0.19 three-argument constructor shape for the default
    # English/studio case (fake jobs and older callers rely on it).
    job_kwargs = {}
    if language != "en":
        job_kwargs["language"] = language
    if motion_template != "studio":
        job_kwargs["motion_template"] = motion_template
    job = RenderJob(offer_id, api_url, out_root, **job_kwargs)
    kwargs = {
        "capture_video": None,
        "preset_keys": missing,
        "skip_narration": skip_narration,
        "capture_id": candidate.get("capture_id"),
    }
    # Keep the v0.19 FakeJob-compatible call shape for English, while a
    # non-English candidate renders only its own language.
    if language != "en":
        kwargs["languages"] = (language,)
    job.run(**kwargs)
    return True


def _jobs_enabled() -> bool:
    return os.environ.get("MTK_RENDER_JOB_QUEUE", "1").strip().lower() \
        not in {"0", "false", "no"}


def _ensure_render_jobs(client: httpx.Client, candidates: list[dict]) -> int:
    """Record owed render work in the durable queue (best effort).

    Dedupe key binds to the EXACT script version (`render:{offer}:{lang}:
    {script_hash}`), so a rewritten script naturally creates a NEW job and a
    rendered candidate never re-queues the old one. Failures here never stop
    the sweep — the derived candidate list stays authoritative. Returns the
    number of jobs confirmed present."""
    if not _jobs_enabled() or not candidates:
        return 0
    present = 0
    for candidate in candidates:
        key = "render:{}:{}:{}".format(
            candidate["offer_id"], candidate.get("language") or "en",
            candidate.get("script_version_hash") or candidate.get("script_version") or "0")
        try:
            resp = client.post("/jobs", json={
                "kind": "render_package",
                "entity_id": candidate["offer_id"],
                "payload": {"offer_id": candidate["offer_id"],
                            "language": candidate.get("language") or "en",
                            "script_version": candidate.get("script_version")},
                "dedupe_key": key[:300], "max_attempts": 5,
            })
            if resp.status_code < 300:
                present += 1
            elif resp.status_code == 404:
                return 0  # older API without the jobs queue
        except httpx.HTTPError as exc:
            log.warning("render job sync failed (%s) — sweep-only this run", exc)
            return 0
    return present


RENDER_LEASE_S = int(os.environ.get("MTK_RENDER_LEASE_S", "3600"))
RENDER_LEASE_TOUCH_S = int(os.environ.get("MTK_RENDER_LEASE_TOUCH_S", "600"))


def _lease_keeper(client: httpx.Client, job_id: str, stop: threading.Event,
                  holder: str = "render-worker",
                  lost: threading.Event | None = None) -> None:
    """Renew the render job's lease while the encode runs (WP-G §5.6.6).

    A 4K encode can outlive the one-hour claim lease; without renewal the
    attention view flags the job as wedged and a lease-expiry decision could
    fight an in-flight render. The keeper extends the SAME holder's lease
    every RENDER_LEASE_TOUCH_S until the render finishes or the process dies
    (a dead process stops touching → the lease genuinely expires, as before).

    A 409 means this process no longer holds the lease (expired and taken
    over, or reset by an operator): `lost` is set so the caller does not
    report an outcome for work it no longer owns.
    """
    while not stop.wait(RENDER_LEASE_TOUCH_S):
        try:
            resp = client.post(f"/jobs/{job_id}/touch",
                               json={"worker": holder,
                                     "lease_s": RENDER_LEASE_S})
            if resp.status_code == 409:
                log.error("render job %s: lease lost (%s) — this render will not "
                          "report an outcome", job_id, resp.text[:200])
                if lost is not None:
                    lost.set()
                return
            if resp.status_code != 200:
                log.warning("lease renewal for render job %s refused (%s)",
                            job_id, resp.status_code)
        except httpx.HTTPError as exc:
            log.warning("lease renewal for render job %s failed: %s", job_id, exc)


def _drain_render_jobs(client: httpx.Client, api_url: str, out_root: Path,
                       preset_keys: list[str], skip_narration: bool,
                       motion_template: str, candidates: list[dict]) -> set:
    """Claim render_package jobs and render those candidates. Fail-open to
    the classic sweep: queue unreachable / older API / claim refused all
    degrade to sweep-only, and the render gates at the API stay fail-closed.
    Returns the (offer, language) keys rendered here, so the classic sweep
    skips them instead of rendering twice off its stale candidate list."""
    if not _jobs_enabled() or not candidates:
        return set()
    by_key = {(c["offer_id"], c.get("language") or "en"): c for c in candidates}
    rendered_keys: set = set()
    holder = lease_holder("render")
    for _ in range(50):  # bounded per sweep; results remove claimed jobs
        try:
            resp = client.post("/jobs/claim", json={
                "worker": holder, "lease_s": RENDER_LEASE_S,
                "kinds": ["render_package"]})
        except httpx.HTTPError:
            return rendered_keys
        # re-check the kill switch between candidates
        current = _load_policy(client)
        if current is not None and not _render_stage_allowed(current):
            log.info("render stage changed mid-drain — queue drain stopped")
            return rendered_keys
        if resp.status_code != 200:
            return rendered_keys
        try:
            body = resp.json()
        except ValueError:
            return rendered_keys
        if not body.get("claimed"):
            return rendered_keys
        job_id = body["id"]
        offer_id = body.get("entity_id")
        language = (body.get("payload") or {}).get("language") or "en"
        candidate = by_key.get((offer_id, language))
        if candidate is None:
            # rendered meanwhile / offer state moved on / script superseded:
            # the derived list no longer owes this render.
            _job_result(client, job_id, ok=True,
                        detail="no longer a render candidate — nothing owed",
                        worker=holder)
            continue
        keeper_stop, lease_lost = threading.Event(), threading.Event()
        keeper = threading.Thread(
            target=_lease_keeper,
            args=(client, str(job_id), keeper_stop, holder, lease_lost),
            name=f"lease-keeper-{str(job_id)[:8]}", daemon=True)
        keeper.start()
        try:
            _render_candidate(api_url, out_root, skip_narration, motion_template,
                              candidate, preset_keys)
            if not lease_lost.is_set():
                _job_result(client, job_id, ok=True, detail="rendered", worker=holder)
            rendered_keys.add((offer_id, language))
        except SystemExit as exc:
            if not lease_lost.is_set():
                _job_result(client, job_id, ok=True, detail=f"skipped: {exc}",
                            worker=holder)
        except Exception as exc:  # noqa: BLE001 — one candidate never stops the drain
            log.exception("render job %s failed for offer %s", job_id, offer_id)
            if not lease_lost.is_set():
                _job_result(client, job_id, ok=False, detail=f"render failed: {exc}",
                            retry_after_s=300, worker=holder)
        finally:
            keeper_stop.set()
    return rendered_keys


def _job_result(client: httpx.Client, job_id: str, *, ok: bool,
                detail: str | None = None, retry_after_s: int | None = None,
                worker: str | None = None) -> None:
    payload: dict = {"ok": ok}
    if worker:
        payload["worker"] = worker  # lease fencing: only the holder settles
    if detail:
        payload["detail"] = detail[:1900]
    if retry_after_s is not None:
        payload["retry_after_s"] = max(1, min(int(retry_after_s), 86400))
    try:
        client.post(f"/jobs/{job_id}/result", json=payload)
    except httpx.HTTPError as exc:
        log.warning("could not report result for render job %s: %s", job_id, exc)


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
        # Follow X-Next-Cursor: a fixed first page hid every older candidate
        # once the backlog grew beyond `limit`.
        candidates = list(iter_pages(
            client, "/render-candidates",
            {"presets": ",".join(preset_keys)}, limit=limit,
        ))
    except (httpx.HTTPError, ValueError) as exc:
        log.error("render sweep skipped (API unreachable): %s", exc)
        return 0

    # Durable owed-work record (v0.33): mirror the derived candidates into the
    # jobs queue (best effort), then drain what the queue drives. The derived
    # list stays authoritative — a candidate reappears after a restart by
    # recomputation, so lost work is impossible even without the queue.
    synced = _ensure_render_jobs(client, candidates)
    drained_keys = _drain_render_jobs(client, api_url, out_root, preset_keys,
                                      skip_narration, motion_template, candidates)
    if synced or drained_keys:
        log.info("render queue: %d job(s) tracked, %d rendered via the job drain",
                 synced, len(drained_keys))

    rendered = 0
    for candidate in candidates:
        if (candidate["offer_id"], candidate.get("language") or "en") in drained_keys:
            continue  # already rendered via the queue drain this sweep
        # The kill switch is re-checked before each irreversible render, so a
        # pause during a long sweep takes effect immediately.
        current = _load_policy(client)
        if current is not None and not _render_stage_allowed(current):
            log.info("render stage changed to %s — stopping the sweep before the "
                     "next render", "paused" if current.get("paused") else "not auto")
            break
        try:
            if _render_candidate(api_url, out_root, skip_narration, motion_template,
                                 candidate, preset_keys):
                rendered += 1
        except SystemExit as exc:
            log.error("render sweep: %s skipped — %s", candidate["offer_id"], exc)
        except Exception as exc:  # noqa: BLE001 — one candidate never stops the sweep
            log.exception("render sweep: %s failed: %s", candidate["offer_id"], exc)
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
    ffmpeg_path = shutil.which(FFMPEG_PATH) or FFMPEG_PATH
    hb = WorkerHeartbeat(
        args.api, "render",
        metadata={"toolchain": {"ffmpeg": ffmpeg_path}},
    )

    presets = [k.strip() for k in args.presets.split(",") if k.strip()]
    languages = tuple(k.strip() for k in args.languages.split(",") if k.strip())
    for language in languages:
        if language not in ("en", "ur"):
            raise SystemExit(f"unknown language '{language}' — known: en, ur")

    if args.sweep:
        if not args.watch:
            hb.beat("ok", detail="one-shot render sweep")
            try:
                sweep(args.api, Path(args.out), presets, args.skip_narration, args.limit,
                      args.motion)
            finally:
                hb.beat("stopped", detail="one-shot render sweep complete")
            return
        hb.start()
        try:
            while True:  # service mode: the render queue is self-serving
                sweep(args.api, Path(args.out), presets, args.skip_narration, args.limit,
                      args.motion)
                time.sleep(max(30, args.interval))
        finally:
            hb.stop()
    if not args.offer:
        raise SystemExit("pass --offer <OFFER_ID> or --sweep")

    hb.start()
    try:
        RenderJob(args.offer, args.api, Path(args.out),
                  language=languages[0], motion_template=args.motion).run(
            capture_video=args.video,
            preset_keys=presets,
            skip_narration=args.skip_narration,
            capture_id=args.capture,
            languages=languages,
        )
    finally:
        hb.stop()


if __name__ == "__main__":
    main()
