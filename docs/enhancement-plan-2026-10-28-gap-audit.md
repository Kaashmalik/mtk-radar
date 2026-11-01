# MTK Radar: Gap Audit and Production-Readiness Plan — 2026-10-28

Companion to [`enhancement-plan-2026-10-24-evidence-to-video.md`](enhancement-plan-2026-10-24-evidence-to-video.md)
and [`ep-implementation-log.md`](ep-implementation-log.md). This audit compares
every documentation claim with the code at commit `0d3b043`. It is a
read-through audit: the test suite was **not** re-run for it (counts quoted in
other docs are their own logged results, not re-proven here).

## Verdict

The foundation is strong and EP-00…EP-04 are genuinely landed with commit
evidence that matches the code. However, the README roadmap marks every phase
✅ while **EP-05 (video), EP-06 (one-click scheduling) and EP-07 (robustness)
have not started** — and those are exactly the parts that make the system
"fully automated, Full HD and robust".

## P0 — before any feature work

| # | Issue | Action | Owner |
|---|---|---|---|
| H1 | `docs/marshmallow-contact-location-…json` (≈370k lines) is a customer/technician contact & location archive committed to a **PUBLIC** repository. It is unrelated to this product. Deleting it on `main` does not remove it from git history. | Make the repo private **or** purge with `git filter-repo` + force-push, then rotate anything referenced. | Owner decision — not touched by contributors |
| H2 | GitHub Actions blocked by an account billing lock since EP-00; every "green" since then is a local run. | Resolve billing. | Owner |
| H3 | README roadmap shows all phases ✅. | Point status to the EP table/log; mark EP-05…07 open. | Contributor |

## Open gaps (verified in code)

### A. Video quality — "Full HD, realistic" (EP-05, not started)

| ID | Gap | Evidence | Fix |
|---|---|---|---|
| V1 | Capture source is weak | `workers/capture/main.py` records via Playwright `record_video` (low-bitrate VP8 webm); 1080p export cannot restore detail | ffmpeg (`gdigrab`/`x11grab`) or OBS capture at 1080p30/60 near-lossless; Playwright only navigates |
| V2 | Bitrate low for screen text | `workers/render/presets.py` landscape `maxrate 5000k` | 8–12 Mbps 1080p30, screen-content tune |
| V3 | Delivery flags implicit | `workers/render/render.py` had no `-pix_fmt yuv420p`, `-profile:v high`, GOP, colour tags; QC only warns | Explicit, platform-safe H.264 High / yuv420p / BT.709 / 2 s GOP |
| V4 | Loudness measured, never corrected | `workers/render/qc.py` measures `loudnorm`; render never applies it | Loudness normalization in the render (−14 LUFS, −1 dBTP), then QC verifies |
| V5 | Vertical legibility | 16:9 shrunk to 1080×608 on blur → code/UI text tiny | Keyframed crop/zoom per scene ("callout region"); letterbox as fallback |
| V6 | Explainers cannot render | `render/main.py` exits "no capture video" | Explainer track: source cards, allowed public-page screenshots, diagrams, VO, captions |
| V7 | No scene manifest/editor | flat edit manifest only | Scene manifest (claim IDs, asset hash, in/out, crop, captions, citation) + beat editor |
| V8 | TTS cache stores a worker-local path (G25) | `workers/render/narration.py` | Content-addressed audio in object storage; key includes provider/model/voice/speed/version |
| V9 | Caption width is an estimate | system-review deferred P3 | Font-metric measurement (required for Urdu Nastaliq) |

### B. Scheduling & publishing (EP-06, not started)

- **G19** `ScheduleForm.tsx` sends one shared account/render for all platforms (API supports `per_platform`); all four targets always selectable.
- **G20** `BatchApprove.tsx` keeps approve and queue separate; drafts excluded; no preview→commit with idempotency key + package hashes.
- **G23** TikTok adapter direct-posts `SELF_ONLY` without `creator_info` / consent UI. Default must be an export bundle + native/manual scheduling until the app is audited.
- **G24** `hashtags.py` still says YouTube "ignores the rest past 15"; "trending" labels need provenance.
- **G26** Calendar conflicts are page-local and day-bucketed (no accounts, misses midnight).
- **Q1** No bucketed YouTube quota reservation ledger.

### C. Robustness (EP-07, not started)

- Render lease (3600 s) never renewed → >1 h encode can be double-claimed. Add lease heartbeat + fencing.
- No per-account circuit breakers; no durable notification/cost-telemetry outbox.
- No failure-injection contracts (timeout, duplicate delivery, Redis/API outage, expired token, worker death).
- Dashboard can render "empty" during an outage instead of "unavailable".

### D. EP-03 / EP-04 leftovers

- Dashboard does not surface `content_type`, research briefs or the claim editor (API only).
- `research_claims.recheck_at` missing from the attention due-list.
- Extension never exercised in a real Chrome profile.

### E. Deferred P2 items from the 2026-10-23 review

Analytics cache hit/miss type drift (Decimal→str); trends `summary` page-local
but reads as totals; fact-pack not re-checked at render time; release gate
does not recompute thumbnail-text parity.

### F. Cost

- Defaults are older models (`VERIFY_LLM_MODEL=gpt-4o-mini`, `tts-1`); make provider/model explicit, add a free local English TTS option (Piper/Kokoro — verify each voice licence), use paid TTS only for final renders.
- Track cost per **unique video package**, not per schedule.
- Keep paid AI capped (~$5/month proposed) and off by default; budget gate is already fail-closed.

### G. Dashboard UI/UX

- Hand-rolled CSS without a token system for light/dark, motion or focus states.
- Pages lack consistent loading/empty/error/unavailable states and keyboard/ARIA polish.
- Settings renders default "running / assisted" state while the API is
  unreachable — must show "unavailable" instead (same class as §C).
- Target: one design-token layer (colour, type scale, radius, elevation, motion), dark mode, reduced-motion support, accessible focus rings, skeleton loaders and subtle transitions — no heavy UI framework required.

## What "fully automated" can honestly mean

- **Automatic:** discovery, trend scoring, evidence capture of public pages, scripts, explainer video, QC, packaging, YouTube scheduling, metrics.
- **Human by design (enforced):** `verified` on ambiguous evidence; login/2FA/payment in claim walkthroughs; redaction review; final approval in Assisted mode.
- **Platform-blocked today:** unattended TikTok posting (needs audit) and private Instagram posts.

## Milestones

| # | Milestone | Scope | Estimate | Status |
|---|---|---|---|---|
| M0 | Hygiene | H1 (owner), H2 (owner), H3 README status | 0.5 d | H3 done; H1/H2 owner |
| M1 | Full HD encoding | V2, V3, V4 + tests on argv/filters | 1–2 d | **done** (`1d93070`); real-encode proof pending ffmpeg |
| M2 | Capture v2 | V1 + public-page capture worker with URL recipes | 2–3 d | V1 **done** (`625d62b`, opt-in FFmpeg recorder, correct media types); public-page recipe worker open |
| M3 | Explainer track & scenes | V5–V9 | 4–6 d | V6 + scene manifest **done** (`d3fb9e6`), V5 for explainers (`346851a`); keyframed reframing of real captures, beat editor, V8 shared TTS assets, V9 font metrics open |
| M4 | One-click scheduling | G19, G20, G23, G24, G26, Q1 | 3–4 d | G19/G20 (`3711698`), G23/G24 (`1c111f0`), G26 (`3e20862`) **done**; Q1 quota ledger + TikTok consent UI open |
| M5 | Robustness | §C | 3–4 d | lease fencing (`2174805`), circuit breaker (`47c4393`), outage states (`3e20862`) **done**; durable notification/cost outbox + failure-injection suite open |
| M6 | Research UI | §D | 2 d | **done** (`2c5fcf2`); real-browser extension smoke open (owner) |
| M7 | Cost | §F | 1–2 d | **done** (`a8bf53c`): unique-video economics, verified-local free TTS |
| M8 | Dashboard design system | §G | 2–3 d | shell/tokens/themes/motion (`e6df684`), legacy palette → tokens, schedule/review/research UIs **done**; remaining per-page inline-style cleanup open |
| M9 | Proof | integration+e2e on real Postgres, one real private YouTube post, real-browser extension smoke; update the EP log | 1–2 d | open |

Total ≈ 20–29 developer-days. Progress is recorded in
[`ep-implementation-log.md`](ep-implementation-log.md) with executed vs
unproven checks, following the existing convention.

## Second implementation pass (2026-10-28) — previously open items

| Item | Commit | Notes |
|---|---|---|
| EP-07 durable outbox (cost telemetry + notifications) + failure-injection tests | `5331ba2`, `e09d869` | migration 041 `usage_events.event_id`; compose `outbox-data` volume |
| G25/V8 shared, content-addressed, sha256-verified narration audio | `fb5761e` | needs `MTK_STORAGE_BACKEND` to share across hosts |
| Q1 YouTube quota reservation ledger | `998bfdf` | migration 042; copy real limits/costs from the Cloud console |
| G23 UX TikTok creator info + consent screen | `7307887` | migration 043; consent enforced by the worker |
| V9 font-measured caption widths | `e71aa76` | Pillow pinned; install the Urdu Nastaliq face for Urdu |
| V5 activity-following vertical reframing | `b2be8a8` | opt-in `MTK_VERTICAL_REFRAME=auto` |

## Still open

1. **Owner:** ~~H1 (personal-data export in a public repo)~~ — **resolved
   2026-11-01**: history purged and force-pushed; the remaining owner action
   is deleting the pre-rewrite backup bundle after verification (see the
   2026-11-01 section below and the incident log in
   [security-and-redaction.md](security-and-redaction.md)). H2 (Actions
   billing) is still open.
2. **M9 proof on a full machine:** follow
   [`verify-at-home-2026-10-28.md`](verify-at-home-2026-10-28.md) — Postgres
   integration tests, real FFmpeg renders, one private YouTube post.
3. **Validate then decide defaults:** run `MTK_VERTICAL_REFRAME=auto` on a
   few real captures before making it the default.
4. ~~Storyboard editor (V7 UI) and public-page capture worker (M2 second
   half)~~ — **done** in the third pass (`b0a8ca1` + UI commit): versioned,
   ledger-locked storyboard in Studio; sandboxed page screenshots as scenes.

## 2026-11-01 production-readiness pass

A five-way production-readiness review re-checked this audit item by item
against the tree. **Verdict:** the audit items are **verified fixed in code**
— every milestone M0–M8, including the leftovers listed above (storyboard
editor, page-capture worker, quota ledger, TikTok consent, font-measured
captions, reframing, durable outbox), has a landed implementation. What
remains open is **execution proof, not missing features**:

- a **live private/test post per provider** — PROOF-05, needs the owner's
  OAuth keys;
- a **dated real-render QC artifact** — PROOF-06, needs one real encode;
- a **green CI run** — PROOF-04; the GitHub Actions billing lock persists,
  so no CI claim is made anywhere;
- **migrations 041→044 on a real database** (last full real-runner proof,
  2026-10-25, covered 001→040) — `db_migrate.py` enforces numbering and
  refuses gaps;
- a **full `pnpm verify` re-run** after today's fixes.

Also on **2026-11-01** the repository history was purged (issue **H1**) and
force-pushed — see the incident log in
[`security-and-redaction.md`](security-and-redaction.md). H2 (Actions
billing) remains an owner action.

### Same-pass robustness/deploy fix set (knob per guardrail)

| Fix (2026-11-01 pass) | Guardrail / knob |
|---|---|
| Compose boots from the deployment env file (`docker compose --env-file infra/.env …`) so `scripts/deploy.sh`'s generated secrets actually reach every service; the compose file fails fast when `POSTGRES_PASSWORD` is unset instead of falling back to a dev default | `POSTGRES_PASSWORD` (required; minted into `infra/.env` by `scripts/deploy.sh`) |
| API startup guard — the API refuses to run unauthenticated outside dev-open mode | `MTK_ALLOW_UNAUTHENTICATED=1` (explicit opt-in for a sealed local network) |
| Public HTTPS without exposing the API: cloudflared `tunnel` compose profile publishes only the dashboard (the API keeps its `127.0.0.1` bind); proxy notes under `infra/proxy/` | `MTK_TUNNEL_TOKEN` (tunnel connector token) |
| FFmpeg delivery encodes are bounded by a hard wall-clock timeout and the lease is capped, so a wedged encode fails the job visibly instead of holding the lease forever; the render worker handles SIGTERM and stops cleanly | `MTK_RENDER_ENCODE_TIMEOUT_S` (+ existing `MTK_RENDER_LEASE_S`) |
| Legacy media-path serving is confined — a legacy row can no longer make the API stream arbitrary readable host files | `MTK_STORAGE_BACKEND` / `MTK_STORAGE_LOCAL_ROOT` (managed storage roots) |
| Request size + rate middleware: bounded request bodies; the v0.33 auth brute-force throttle (429 budget per IP) stays in force | enforced in middleware, no knob to relax by default |
| Automation-actor attribution: non-human callers are recorded as `automation:<stage>` / `system:` identities and can never appear as a human reviewer in `audit_log` | existing credential-class matrix (`api_hardening.py`) |
| Publishing/collector `ValueError` guards: malformed config or metadata pins the post/job into an actionable failed state instead of crashing the sweep loop | failures recorded in `audit_log` / job outcome, never silent |
| TikTok uploads above the single-chunk cap (≤64 MiB) are refused **up front** with an actionable message; no chunked upload exists yet — export a shorter/split edit | `MAX_SINGLE_CHUNK_BYTES` (`workers/publishing/platforms/tiktok.py`) |
| Dashboard ships a standalone production build (no runtime `npm install`) with its `/api/health` liveness probe | `output: "standalone"` (`apps/dashboard/next.config.ts`) |
| Extension terminal failures (401/422/…) cap out and are abandoned visibly instead of retrying forever | `MAX_ATTEMPTS = 5` (`apps/extension/core.js`) |

Owner-side actions from the same review (code cannot do these): mint
secrets/tokens, provider OAuth consent, set `MTK_TUNNEL_TOKEN`, delete the
pre-rewrite git backup bundle after verifying the rewritten history, and
re-clone/reset existing clones. The live gate list is
[`production-readiness-2026-11-01.md`](production-readiness-2026-11-01.md).
