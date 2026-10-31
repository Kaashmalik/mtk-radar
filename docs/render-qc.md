# Render QC — measured evidence before publishing

Version 0.29 adds a measured render-quality gate. A video is not publishable just
because FFmpeg exited zero: the render worker probes the exact output bytes,
fully decodes them, checks picture/audio events and loudness, validates the
burn-in captions, and stores the report with the render row.

The gate is deliberately fail-closed:

| status | qc_status | schedule | publish |
| --- | --- | --- | --- |
| `rendered` | `passed` | allowed | allowed |
| `qc_failed` | `failed` | refused | refused |
| `render_failed` | `failed` | refused | refused |
| legacy row | `not_checked` | refused | refused |

Existing renders from before migration 023 are **not** silently trusted. They
must be re-rendered so the measured report exists. This is intentional.

## Checks

`workers/render/qc.py` runs seven checks against every preset output:

1. **Measured stream metadata** — FFprobe JSON: container, duration, video
   codec, exact width/height, frame rate, pixel format, bitrate, audio stream
   count/codec/sample rate/channels/bitrate. Wrong aspect, a truncated file or
   a missing narration track fails.
2. **Full decode** — FFmpeg decodes video and optional audio to `-f null -`.
   Decoder errors fail even if the encoder returned zero.
3. **Black and freeze events** — `blackdetect` and `freezedetect` identify
   accidental black frames and stuck/static video.
4. **Silence** — `silencedetect` catches narration/demo dead air.
5. **Loudness and peak** — `loudnorm` measures integrated LUFS and true peak.
   Defaults: −16 LUFS ±1 LU, true peak ≤ −1 dBTP.
6. **Caption safe area and overflow** — the burn-in ASS file is parsed per
   preset: side margins, text width, wrapping, number of lines and vertical
   position must stay inside the safe area. Layout validation uses a
   conservative font-width estimate, so it is deterministic and needs no
   Chromium or image OCR.
7. **Persisted report + dead letter** — the JSON report (tool versions,
   thresholds, measured values, events, errors/warnings) is stored in
   `renders.qc_report`. Failed attempts stay in `renders` with
   `status=qc_failed`/`render_failed` and appear in **Queue → Render QC &
   dead letter** (`GET /render-dead-letter`). `/analytics` also exposes
   rendering counts.

## Intentional stills and official pages

A static official terms page can legitimately look frozen. Annotate the exact
time ranges rather than disabling the check globally:

```json
[
  {"start": 12.5, "end": 19.0, "reason": "official terms page shown"},
  {"start": 31.0, "end": 38.0, "reason": "static pricing screenshot"}
]
```

Set `MTK_RENDER_QC_EXEMPT_RANGES` to that JSON, or put the same list under
`"qc_exempt_ranges"` in the script metadata. Ranges subtract from detected
black/freeze/silence intervals; only the uncovered portion is compared with the
threshold.

## Thresholds

Every value has an environment override; see [`.env.example`](../.env.example).
The important defaults:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MTK_RENDER_QC_TARGET_LUFS` | `-16` | integrated loudness target |
| `MTK_RENDER_QC_LUFS_TOLERANCE` | `1` | ± LU tolerance |
| `MTK_RENDER_QC_MAX_TRUE_PEAK` | `-1` | maximum dBTP |
| `MTK_RENDER_QC_REQUIRE_AUDIO` | `1` | narration-required output |
| `MTK_RENDER_QC_MAX_BLACK_S` | `1` | unexplained black segment |
| `MTK_RENDER_QC_MAX_FREEZE_S` | `5` | unexplained frozen segment |
| `MTK_RENDER_QC_MAX_SILENCE_S` | `2` | unexplained silent segment |
| `MTK_RENDER_QC_CAPTION_SAFE_FRACTION` | `0.03` | safe-area inset |
| `MTK_RENDER_QC_DECODE_TIMEOUT_S` | `300` | full-decode timeout |

Thresholds are account-neutral starting points. If a specific format needs a
different policy, change the environment and record why; do not edit a passing
report by hand.

## Operating a QC failure

1. Open **Queue → Render QC & dead letter** and read the blocking reason.
2. Fix the source: correct audio level/clipping, remove dead air or stuck
   frames, recapture a broken segment, or annotate a genuinely static page.
3. Re-render the offer. A failed attempt does **not** make the render
   candidate disappear, so the sweep can retry it.
4. Schedule only after a new row shows `rendered / passed`.

The publisher also re-checks the pinned render immediately before upload, so a
stale schedule that pinned a failed or legacy render is paused, not uploaded.

## Scope and limits

This gate covers deterministic media quality. It does **not** replace the
human redaction review, OCR/transcript leak checks, factual claim checks, mobile
device previews or golden-clip regression tests. Those remain separate
release-blocking work in WP09. QC failures are evidence for a human fix, never
permission to bypass a gate.

## Delivery encoding and the explainer track (2026-10-28)

- **Normalization before measurement.** The render applies `loudnorm` at the
  QC target (`MTK_RENDER_QC_TARGET_LUFS`, default −16 LUFS; true peak 0.5 dB
  under `MTK_RENDER_QC_MAX_TRUE_PEAK`) and resamples to 48 kHz, so loudness QC
  verifies a corrected track instead of rejecting an uncorrected one.
- **Explicit delivery flags.** H.264 High@4.2, `yuv420p`, BT.709 tags, a
  2-second GOP, CRF 18 with a 12 Mbps cap for both 1080p presets
  (`MTK_RENDER_X264_PRESET` trades encode time for size).
- **Research explainers** (current brief `content_type = explainer`, script
  format `official_explainer`) render without a capture: claim cards over a
  mid-tone, lightly grained background with fades, one natively composed base
  per orientation, and `assets/explainer/scene_manifest.json` (sha256 logged).
  The background is deliberately not black and never static, so black-frame
  and freeze checks pass on their merits — no exemption ranges are used.
  Contradicted claims are never shown; unknown claims are labelled.

## Caption width measurement (V9)

Caption QC measures every wrapped line with the font file libass will use
(`MTK_CAPTION_FONT_FILE`, else `fc-match`, else the usual font folders), via
Pillow (Raqm shaping for Urdu when available), scaled by libass's rule that an
ASS font size equals ascender + descender. The QC report's
`width_method` says `font:<file>` or `estimate`; the estimate (0.60 × size
per character) is only a labelled fallback when the font or Pillow is
missing. For Urdu, install the Nastaliq face on the render host so both the
burn-in and the measurement use it.

