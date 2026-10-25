# 2026 YouTube Playbook — mtk-radar mapping (2026-10-23)

The 2026 channel master plan (sub-niche selection, minimal-tags metadata,
phone-safe packaging, retention-first editing, 30-day launch cadence) mapped
onto what mtk-radar **enforces**, what it **generates deterministically**, and
what stays an **operator action**. Every "enforced" item is a release-gate
problem: an empty problem list is the only permission to release.

Sources: 2026 master plan (user-provided), `docs/enhancement-plan-2026-10-22.md`,
`services/api/seo.py`, `workers/render/covers.py`, `services/api/release_gate.py`.

---

## 1. Niche & topic selection

| Master plan rule | Platform behavior |
|---|---|
| Sub-niche over generalist | **Operator.** The niche lives in brand settings (channel name, categories). The generator only packages verified offers in the configured categories — it cannot drift off-niche because every video is bound to a verified offer. |
| "3-competitor" rule (10k–100k subs, views > subs = trending) | **Operator-measured, platform-scored.** The radar applies the rule deterministically: record competitor stats via the radar's "3-competitor check" (`POST /trends/{id}/competitors`) and demand is bumped *only* when ≥ 3 similar channels in the 10k–100k band out-perform their subscriber count (`signals.competitor_evidence`, plus a driver/risk in `score_reason`). The platform never scrapes YouTube for this — the numbers must be human-measured. |
| Google Trends / YouTube Research "Content Gaps" / Reddit + TikTok monitoring | **Operator.** Radar candidates are entered via the studio; the platform never auto-picks a topic without a verified offer behind it. |

## 2. Tags & metadata (2026 framework)

Master plan: tags play a minimal role — spend 1 minute; titles hook in ≤50
chars; thumbnails ≤3 words never repeating the title; descriptions native for
humans with the keyword in the first 20 words; 5–8 plain tags (1 broad + 2–4
specific + channel name).

| Rule | Platform behavior |
|---|---|
| Title ≤50 characters (mobile truncation) | **Generated + enforced for pinned variants.** `seo.py` builds YouTube titles with a 50-character target (`YOUTUBE_TITLE_TARGET`), trimming on word boundaries; the release gate blocks a pinned metadata variant whose title exceeds 50 (`metadata_title_too_long`). Non-variant metadata is not gate-checked. The 100-char platform ceiling remains a hard cap only. |
| 5–8 plain tags: 1 broad + 2–4 specific + channel name | **Generated; channel suffix is PLANNED.** `build_youtube_tags()` derives the broad category keyword (e.g. `free domain`), a dated sub-keyword (`free domain 2026`), and the provider. The `channelName` suffix is not wired from brand settings — it is only supplied by tests. No `#` prefixes — hashtags live in the description. The gate blocks out-of-band tag lists (`metadata_tags_invalid`) and hashtag-style tags (`metadata_tags_hashtags`). |
| No misleading/irrelevant tags (algorithm penalty) | **Mostly structural.** Tags derive from an offer field, the category or a fixed phrase; the generator still emits static words such as `verified walkthrough` and a hardcoded `2026`, so "never invents offer facts" is too strong. |
| Thumbnail ≤3 words, never repeating the title, readable on a phone | **Generated + enforced.** `build_thumbnail_text()` (identical logic in `services/api/seo.py` and `workers/render/covers.py`) picks the single most specific verified fact — promo code, or value amount + currency — filtered against title words, falling back to the verified badge. The renderer draws that text big (full title only for the aria-label); the gate blocks an approved cover whose text exceeds 3 words (`thumbnail_text_too_long`). |
| Description: first 2 lines native for humans, keyword in first 20 words | **Generated.** Openers lead with the offer title/provider and the plain-language value line before eligibility boilerplate; the tracked website link and CTA follow. Not gate-enforced (no reliable automated keyword test) — reviewed in studio playback/packaging review. |
| Tags = 1 minute of effort | **Automated.** Generated per offer/language; zero operator time. |

## 3. Video quality & production standards

| Master plan rule | Platform behavior |
|---|---|
| Audio quality non-negotiable (USB mic / AI cleanup) | **Operator.** Capture QC checks duration, dimensions and audio presence only; loudness and speech-coverage measurement is **PLANNED**, not implemented. Buying the mic, treating the room and the playback sign-off remain human work. |
| 1080p 30/60fps minimum, bright lighting, no face shadows | **Generated (renders are 1920×1080 landscape / 1080×1920 vertical)** + **operator** for lighting when a camera appears in frame. Faceless walkthrough renders are unaffected. |
| Export 4K (upscaled) at high bitrate for the better VP09/AV01 codec | **Operator decision — deliberately not automated.** The render pipeline is deterministic and QC checks are resolution-pinned; silently upscaling would change measured QC semantics. If wanted, re-encode approved renders locally (`ffmpeg -i in.mp4 -vf scale=3840:2160 -c:v libx264 -crf 16 -b:v 40M`) and re-pin the new `video_sha256` through the hash-verification flow before scheduling. |

## 4. Retention-first editing

| Master plan rule | Platform behavior |
|---|---|
| 5-second rule (change something every 5–7s) | **PLANNED.** Scripts are built as timed beats, but the renderer is one continuous pass and does not cut on beat boundaries. Use the beat map as an editing plan. |
| "No-intro" hook — value in the first 5 seconds | **Generated + reviewed.** Script formats open with the claim, not a channel intro. There is **no wording guard** for "welcome back" filler (PLANNED); human playback review validates the hook before sign-off. |
| J-cut / L-cut (audio leads the picture) | **PLANNED.** Narration replaces the capture audio 1:1; there is no `adelay`/`itsoffset` lead-in in the FFmpeg assembly. |
| Functional sound design, music ≈ −25/−30 dB | **PLANNED.** No music/BGM/mix path exists in the workers; the preset mix levels are not implemented. |
| Retention graph → cut boring parts from the next script | **Operator**, supported by the growth loop: per-video metrics (CTR, average view duration, retention) feed the 48h/7d/28d review; script revisions via the studio carry the fix. |

## 5. 30-day launch plan

| Phase | Platform behavior |
|---|---|
| Setup & branding (days 1–5) | **Operator** in YouTube Studio (brand account, avatar/banner, About page). Channel name synced into mtk-radar brand settings so tags/packaging stay branded. |
| Topic batching (days 6–10): 10 ideas from competitor gaps, 4 fully scripted | **Platform supports.** Trend radar → offers → studio generates full packages (script, A/B metadata, covers, captions) per offer; scripts are reviewable/revisable before anything is recorded. |
| Launch (days 11–25): first 2 videos same day, then weekly (e.g. Thursday 3 PM) | **Generated + enforced pipeline.** Scheduling with timezone-aware local time; two same-day schedules or two weekly slots are ordinary schedule rows. The release gate decides "may this go out"; the publishing worker executes. |
| Analyze & pivot (days 26–30): CTR < 4% → change thumbnail/title; AVD < 40% → consult retention graph | **Platform-flagged, operator-decided.** The growth review emits a high-priority "Swap the packaging: CTR is under 4%" recommendation when measured impression CTR averages below 4%, and "Cut the dead segment" when average view duration is below 40% — computed only over actually measured rows (missing data is "unavailable", never a 0). The studio A/B experiments then test the fix one variable at a time. The thresholds never auto-block releases. |

---

## Editing software & format (the plan's closing question)

- **Editing software:** mtk-radar's render stack is a deterministic FFmpeg
  pipeline — no traditional NLE. Every cut, cover, caption and narration mix is
  reproducible from the versioned script + beat spec, which is what makes the
  byte-hash approval chain (`script_version_hash` → `video_sha256`) possible.
- **Long-form, Shorts, or a mix:** the platform ships **both**, as first-class
  presets — `landscape` 1920×1080 (long-form) and `vertical` 1080×1920
  (Shorts) — with per-preset cover layouts. Recommended mix per the playbook:
  weekly long-form walkthrough as the anchor, Shorts cut from the same beats
  as discovery funnels.

## What the platform will *not* do

- It will not invent claims, tags or thumbnail hype beyond verified offer
  fields — that is the documented honesty contract, and the release gate
  fails closed on it.
- It will not silently upscale to 4K or change measured QC semantics (see §3).
- It does not replace the human: playback sign-off and every
  approve/resolve/decide endpoint require the reviewer token; service
  credentials get 403.
