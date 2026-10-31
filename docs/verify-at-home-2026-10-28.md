# Verify on the home machine — 2026-10-28 implementation pass

The office machine had no Docker, Postgres or FFmpeg, so everything below
was **written and unit-tested but not executed** there. Run these steps in
order on the fully set-up home machine. Each step says what "pass" looks like.
Record results in [`ep-implementation-log.md`](ep-implementation-log.md).

Already proven at the office (commit `70650f2` and later): Python unit suite
1014 passed / 4 skipped, `ruff check .`, compileall, filename lint, extension
`node --test` 25/25, `pnpm typecheck`, dashboard `next build`, YAML parse.

## 0. Update and install

```bash
git pull origin main
corepack enable && pnpm install          # pnpm version pinned in package.json
python -m pip install -r services/api/requirements.txt -r workers/requirements.txt \
  -r workers/publishing/requirements.txt -r workers/render/requirements.txt pytest ruff
ffmpeg -version                          # needs libx264, libass (subtitles), loudnorm
```

## 1. Full pipeline (the integration tests nobody has run yet)

```bash
pnpm verify          # lint → tests on a REAL Postgres → typecheck → build → compose → e2e
```

**Pass:** green end to end. The new integration tests to look for by name:

| Test | Proves |
|---|---|
| `test_approve_and_queue_is_atomic_per_target_and_rejects_stale_previews` | G20 one-click approve & queue |
| `test_job_result_is_fenced_to_the_current_holder` | lease fencing |
| `test_attention_lists_due_and_contradicted_research_claims_of_current_brief` | research attention |
| `test_research_explainer_renders_without_capture_only_as_official_explainer` | M3 API gate + candidates |
| `test_cost_per_video_counts_unique_packages_not_cross_posts` | M7 unit economics |
| `test_same_platform_within_an_hour_is_flagged_as_conflict` (existing) | G26 rewrite kept behaviour |
| `test_replayed_usage_event_is_counted_once` | outbox replay dedup (migration 041) |
| `test_youtube_quota_ledger_reserves_atomically_and_refuses_past_the_limit` | Q1 ledger (migration 042) |
| `test_tiktok_options_and_consent_are_part_of_the_hashed_package` | TikTok consent (migration 043) |

If one fails, it is a real defect in that commit — fix the code, not the test.

## 2. Real render of a capture (M1 encoding + loudness)

Start the stack (`docker compose -f infra/docker/docker-compose.yml up -d --build`,
then `exec api python db_migrate.py`), take an offer that has a reviewed
capture, then:

```bash
API_URL=http://localhost:8000 python workers/render/main.py --offer <offer-id> --capture <capture-id>
ffprobe -v error -show_entries stream=codec_name,profile,pix_fmt,color_space,sample_rate \
  -of compact projects/<offer-id>/renders/<offer-id>-landscape.mp4
```

**Pass:** the render row is `rendered / qc passed`; ffprobe shows
`h264 High yuv420p bt709` + `aac 48000`; the QC report's loudness is within
−16 ±1 LUFS. Open the vertical file and check small UI text is readable.

## 3. Real research explainer (M3)

Needs narration (QC requires audio). Cheapest: a local TTS server, e.g.
Kokoro-FastAPI on `http://localhost:8880/v1`, with `TTS_BASE_URL` pointed at
it, `TTS_API_KEY` empty and `TTS_LOCAL=1`.

1. Promote a trend in the dashboard (Radar) → it gets research brief v1.
2. Add claims to the brief, set statuses on the offer page (#research),
   verify the offer, generate the script (format `official_explainer`).
3. `python workers/render/main.py --offer <offer-id>` (no `--capture`).

**Pass:** `projects/<id>/assets/explainer/{base.mp4,base-vertical.mp4,scene_manifest.json}`
exist; both renders pass QC (no black/freeze failures); contradicted claims
are absent; the vertical export shows full-size cards; Settings → Costs shows
the TTS usage at $0 with provider `local`.

## 4. High-quality capture (M2, optional)

```bash
MTK_CAPTURE_BACKEND=ffmpeg python workers/capture/main.py --offer <offer-id>
```

**Pass:** a kiosk browser fills the top-left 1920×1080, the session ends with
`capture.mkv`, it plays in the offer page's media player, and capture QA passes.
Keep notifications off — the recorder sees everything in that region.

## 5. Dashboard with live data

`pnpm --filter mtk-radar-dashboard dev`, sign in, then check:

- **Offer page → Schedule:** one target row per platform; Instagram offers
  only Public; TikTok public is labelled "audited app only"; platforms without
  an active account are disabled with the reason.
- **Calendar → Review & queue:** tick a draft, click *Approve & queue*; repeat
  the click → "Already queued — no change".
- **Offer page → Research brief & claim ledger:** set a claim to Contradicted →
  it appears in *Needs You* as an error.
- **Stop the API:** Settings shows "Live data unavailable" (no fake "running"),
  Queue says "Queue unavailable", not "Empty".
- Theme switch (system → light → dark) at the bottom of the sidebar, and the
  mobile drawer at a narrow window width.

## 5b. Second-pass features

- **Quota:** Settings → *YouTube quota today* appears; after a YouTube upload
  the account shows the reserved/consumed units and the Pacific reset time.
- **Outbox:** stop the API, let a render worker report usage, start the API
  again → the usage appears once (check the `outbox-data` volume empties).
- **TikTok:** with a connected TikTok account, wait one publishing sweep →
  the schedule form shows `@handle`, the creator's privacy levels (no
  default), interaction toggles and the consent line; Schedule stays
  disabled until consent is ticked.
- **Captions:** a render's QC report shows `width_method: font:DejaVuSans.ttf`.
- **Vertical reframe:** render one capture with `MTK_VERTICAL_REFRAME=auto`;
  compare the 9:16 export with the default. Keep it opt-in until it looks
  right on several captures.

## 5c. Storyboard editor + public-page capture

1. Integration tests to look for: `test_storyboard_is_versioned_derived_from_the_ledger_and_human_only`,
   `test_page_capture_requests_filter_unsafe_urls_and_record_results` (migration 044).
2. Install the browser once: `pip install -r workers/capture/requirements.txt`
   then `python -m playwright install chromium`, and run the page worker:
   `MTK_API_URL=http://localhost:8000 MTK_WORKER_TOKEN=… python workers/capture/page_capture.py --watch`
   (set `MTK_STORAGE_BACKEND` so screenshots are shared with the render worker).
3. Studio → an explainer offer → **Storyboard** → *Capture public source pages*:
   add the paper URL → after one worker pass it shows `ok` and a **Source page**
   scene with the screenshot. Try `http://…` or an intranet URL: refused with a reason.
4. Reorder scenes, untick one, change durations, edit the opening/closing text,
   **Save storyboard** → v1. Try editing a claim's text: it is locked.
5. Render the explainer: `assets/explainer/scene_manifest.json` shows
   `storyboard_version: 1` and the saved order; the page scene shows the
   screenshot with a slow push-in in both 16:9 and 9:16; QC passes.
6. Mark a used claim *Contradicted* on the offer page → Studio shows the red
   "renderer will drop" notice; the next render omits it and lists it in `dropped`.

## 6. One private YouTube post

Follow [`go-live-checklist.md`](go-live-checklist.md) with privacy **Private**
on YouTube only. **Pass:** the schedule ends `published` + confirmed, the
video is private on the channel, captions and thumbnail attached.

## Owner actions (not code)

- Make the repository private (it contains a customer contact/location export
  in `docs/`; removing it from history needs `git filter-repo` + force-push).
- Resolve the GitHub Actions billing lock so CI runs step 1 on every push.
