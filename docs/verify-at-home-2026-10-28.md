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

## 6. One private YouTube post

Follow [`go-live-checklist.md`](go-live-checklist.md) with privacy **Private**
on YouTube only. **Pass:** the schedule ends `published` + confirmed, the
video is private on the channel, captions and thumbnail attached.

## Owner actions (not code)

- Make the repository private (it contains a customer contact/location export
  in `docs/`; removing it from history needs `git filter-repo` + force-push).
- Resolve the GitHub Actions billing lock so CI runs step 1 on every push.
