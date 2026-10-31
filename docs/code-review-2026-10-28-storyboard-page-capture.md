# Code review — storyboard editor & public-page capture (2026-10-28)

| | |
|---|---|
| **Date** | 2026-10-28 |
| **Scope** | Commits `b0a8ca1` (storyboard engine + page-capture worker, backend) and `218a182` (Studio storyboard editor + capture panel) |
| **Method** | `/code-review` (Claude Code) over `HEAD~2..HEAD`, followed by manual verification of every finding against the code |
| **Result** | 10 findings + 1 cleanup — all confirmed, **all fixed** in 6 commits |
| **Not covered** | The rest of the ~400-file codebase was not swept by this review (see "Next review" below) |

## Summary

| # | Severity | Area | Finding | Status | Fix commit |
|---|---|---|---|---|---|
| 1 | **Critical (security)** | `workers/capture/page_capture.py` | SSRF guard bypass: redirect hops and DNS rebinding could reach private networks | Fixed | `6b5a455` |
| 2 | **Critical (security)** | `services/api/storyboard_api.py`, `media_api.py` | Arbitrary `image_ref` → any readable host file served as an image | Fixed | `ff2a02a` |
| 3 | High (reliability) | `page_capture.py` | Storage/API errors escaped `process()`/`drain()`, killed the worker, left jobs leased | Fixed | `6b5a455` |
| 4 | High (reliability) | `page_capture.py` | Non-2xx result reports ignored; job marked ok, capture stuck "requested" | Fixed | `6b5a455`, `ff2a02a` |
| 5 | High (deployment) | `infra/docker/docker-compose.yml` | No service ran the page-capture worker; no health alert | Fixed | `4dd155d` |
| 6 | High (correctness) | `workers/render/main.py` | Transient storyboard API error → silently rendered the suggestion, not the reviewer's storyboard | Fixed | `89140a3` |
| 7 | High (correctness) | `workers/render/main.py` | Storyboard saved for an older brief → every claim dropped, near-empty video rendered | Fixed | `89140a3` |
| 8 | Medium (UX/data loss) | `StoryboardEditor.tsx` | Capture request reloaded the board and wiped unsaved edits | Fixed | `b667ed0` |
| 9 | Medium (performance/compat) | `workers/render/explainer.py` | Each screenshot decoded + rescaled for the whole video; `t` in `scale` unsupported on older FFmpeg | Fixed | `89140a3` |
| 10 | Low (validation) | `packages/storyboard/__init__.py` | Malformed `claim_ids` raised → HTTP 500 instead of 422 | Fixed | `89140a3` |
| – | Cleanup | `workers/render/explainer.py` | Unused `scenes_from_storyboard` duplicated renderer logic | Removed | `89140a3` |

## Findings and how each was fixed

### 1. SSRF via redirect hops / DNS rebinding (critical)

**Problem.** Playwright's `context.route` sees only the first URL of a
redirect chain, and Chromium resolved DNS itself after our check. A public
page could embed `<iframe src="https://evil.example/r">` that 302-redirects to
`http://169.254.169.254/` (cloud metadata) or an intranet host; the content
would end up in the screenshot and then in a published video. A hostname
that resolves public first and private later (rebinding) passed the same way.

**Fix.** New `workers/capture/egress_proxy.py`: a loopback CONNECT proxy for
the lifetime of one capture. Chromium is launched with
`proxy={"server": proxy.url}` and `--proxy-bypass-list=<-loopback>`, so
**every** connection (redirects, iframes, sub-resources, websockets, even
loopback) goes through it. The proxy:
- accepts only `CONNECT host:443` (plain-HTTP proxying, other ports and
  methods → 403);
- resolves the host itself, requires **every** DNS answer to be public;
- connects to exactly that validated address — the browser never resolves
  DNS, so there is no rebinding window.

The route check and the final-URL check stay as defence in depth.

**How to verify.** `workers/capture/tests/test_egress_proxy.py` (authorize
matrix incl. mixed public/private answers; on-the-wire 403 for private
CONNECT and plain HTTP; tunnel pinned to the validated IP). At home: request
a capture of a page that redirects to `http://127.0.0.1` — the capture is
`refused`/the request is blocked and logged.

### 2. Arbitrary file read through `image_ref` (critical)

**Problem.** `POST /page-captures/{id}/result` accepted any `image_ref` from a
worker/service credential; `/page-captures/{id}/image` served it through the
legacy host-path fallback. A leaked worker token could register
`/app/.env` and download the API host's secrets as `image/png`.

**Fix.** `expected_image_ref_ok()` accepts only this capture's managed key:
`local://pages/<offer>/<capture>.png` or `s3://<bucket>/pages/<offer>/<capture>.png`
(422 otherwise). The image route refuses any non-managed ref (404) — it never
falls back to a host path. The worker now requires object storage
(`MTK_STORAGE_BACKEND`) and never reports a local path.

**How to verify.** `services/api/tests/test_page_capture_refs.py` (8 hostile
shapes) and the integration test posting 4 hostile refs before the valid one.

### 3. Worker crashes on storage/API errors (high)

**Problem.** `storage.put()` sat outside the `try` in `process()` and `drain()`
had no error handling: a MinIO blip or a claim error killed the `--watch`
loop, and the claimed job kept its lease (expired leases are never
auto-reclaimed), stalling every capture in it.

**Fix.** `process()` never raises (storage errors → `failed` result);
`drain()` contains claim/list/job errors and always settles the claimed job
(`ok:false` + 120 s retry on failure); the watch loop catches any sweep crash;
the worker sends a `page-capture` heartbeat.

### 4. Lost results marked as success (high)

**Problem.** `_report()` ignored non-2xx responses and `drain()` always
settled the job `ok:true`, so a refused/failed result left the capture
"requested" forever with nothing retrying it.

**Fix.** `_report()` returns whether the API recorded the outcome (2xx, or
409 = already recorded). If any result is unrecorded the job is settled
`ok:false` with a retry. Additionally the API marks requests no worker
answered within **1 hour** as `failed` with an actionable message
("is the page-capture service running?").

### 5. Page-capture worker not deployed (high)

**Problem.** No compose service ran `page_capture.py --watch`, and
`worker_health` did not expect it, so capture jobs were never processed and
no alert fired.

**Fix.** `workers/capture/Dockerfile` (pinned
`mcr.microsoft.com/playwright/python:v1.49.1-noble`, non-root `pwuser`) and a
`page-capture` compose service (workers profile, 1 GB shm for Chromium,
same storage settings as render). `page-capture` is now an expected worker,
so a missing/stale worker shows in *Needs You*.

**How to deploy.** `docker compose -f infra/docker/docker-compose.yml --profile workers up -d --build page-capture`
with `MTK_STORAGE_BACKEND` set (`local` with the shared `storage-data`
volume, or `s3`).

### 6. Saved storyboard silently replaced by the suggestion (high)

**Problem.** `_storyboard_inputs()` swallowed every exception and returned
`{}`; on a transient 5xx/timeout the render drew the auto-suggestion (all
non-contradicted claims) — a video the reviewer never approved.

**Fix.** Only `404` (an API without the storyboard route) falls back to the
suggestion; any other error raises, so the render job fails, retries and
shows in the render dead-letter/attention view.

### 7. Storyboard saved for an older research brief (high)

**Problem.** Claim ids belong to a brief version. After the research brief
was revised, re-validating the old storyboard dropped every claim scene and
a near-empty explainer was rendered, visible only in a log line.

**Fix.** The renderer refuses a storyboard whose `brief_id` differs from the
current brief ("review and save it again before rendering"), and Studio's
storyboard response lists the same problem so the reviewer sees it before
rendering.

### 8. Capture request wiped unsaved storyboard edits (medium)

**Problem.** The capture panel called the full `load()`, which replaced the
scene list and cleared the dirty flag.

**Fix.** `load(keepScenes)` — after a capture request only the inputs
(captures, claims, problems) refresh; the reviewer's unsaved scenes stay.

### 9. Page overlays decoded and scaled for the whole video (medium)

**Problem.** Each screenshot was looped from `t=0` to its scene end and
Lanczos-rescaled every frame with `eval=frame` even while hidden; the scale
expression used `t`, which older FFmpeg builds do not provide.

**Fix.** Each screenshot is looped only for its own scene (`-t span`), zoomed
with `zoompan` (long-standing filter), faded on its own timeline and placed
with `setpts=PTS-STARTPTS+start/TB`; the per-frame overlay evaluation was
removed. Frames outside a scene are never decoded or scaled.

### 10. Malformed `claim_ids` → HTTP 500 (low)

**Problem.** `validate()` indexed `claim_ids` blindly: `5` → `TypeError`,
`{...}` → `KeyError`, and a string silently looked up its first character.

**Fix.** `_single_id()` accepts exactly one id (a one-item list or
`claim_id`); anything else becomes a 422 problem.

## Commits

| Commit | Message |
|---|---|
| `89140a3` | fix: renderer never swaps the saved storyboard; cheaper page overlays (#6, #7, #9, #10, cleanup) |
| `ff2a02a` | fix(security): page-capture images only from this capture's storage key (#2, stale requests for #4) |
| `6b5a455` | fix(security): pin page-capture egress through a validating proxy; robust worker (#1, #3, #4) |
| `4dd155d` | fix(deploy): run the page-capture worker in compose and monitor its heartbeat (#5) |
| `b667ed0` | fix(ui): capture requests no longer wipe unsaved storyboard edits (#8) |

## Verification status

**Executed on the office machine** (before the final two commits): storyboard
and render suites (149 passed), page-capture suite incl. proxy socket tests
(26 passed), compose env-matrix guard, ruff — all green.

**Not executed (by request, commit `4dd155d` / `b667ed0` pushed without a
re-run; and generally not possible here):** full suite after the last two
commits, dashboard typecheck/build for the editor change, Postgres
integration tests (migration 044 + updated page-capture test), building the
Playwright image, a real Chromium capture, and a real FFmpeg render of page
overlays.

### Run at home (in order)

```bash
git pull origin main
pnpm verify                                   # unit + integration + typecheck + build + e2e
docker compose -f infra/docker/docker-compose.yml --profile workers up -d --build page-capture
```

Then, in Studio → Storyboard → *Capture public source pages*:
1. A public paper URL → `ok` with a screenshot within one worker pass.
2. `http://…`, an intranet host, or a page that redirects to `127.0.0.1` →
   refused/blocked with a reason; no screenshot.
3. Edit scenes (unsaved), request a capture → edits are still there.
4. Save the storyboard, render the explainer → `scene_manifest.json` shows the
   storyboard version; page scenes zoom smoothly; QC passes.
5. Revise the research brief → Studio shows "saved for an older research
   brief"; a render is refused until the storyboard is saved again.
6. Stop the page-capture service for over an hour → its requests turn
   `failed` with the "is the service running?" message, and *Needs You*
   shows the missing worker.

## Next review

The review covered only the storyboard/page-capture commits. Recommended next:
`/review ultra 0d3b043` (all work since the original audit) or a
`/code-review high` per area — publishing worker (quota, TikTok consent,
circuit breaker), outbox, and the render pipeline.
