# Third-Party Notices

Every adopted upstream used by MTK RADAR AI, with the exact version we pin,
its license, how it is integrated, and the obligations that follow.
Companion to [`open-source-integrations.md`](open-source-integrations.md)
(rationale) and the master plan §8 (evaluation rules).

Rule: **never merge upstream application source into this repository.**
Integration happens through pinned packages, pinned images, or APIs.

## Adopted

| Project | Pinned version | License | Integration tier | Notes / obligations |
|---|---|---|---|---|
| FastAPI | `0.115.5` (services/api/requirements.txt) | MIT | Library | Attribution only |
| uvicorn | `0.32.1` | BSD-3-Clause | Library | — |
| asyncpg | `0.30.0` | Apache-2.0 | Library | — |
| pydantic | `2.10.3` | MIT | Library | — |
| pydantic-settings | `2.6.1` | MIT | Library | — |
| httpx | `0.28.1` (workers/requirements.txt) | BSD-3-Clause | Library | The only HTTP client in the workers (no requests/urllib3) |
| feedparser | `6.0.11` | BSD-2-Clause | Library | RSS/Atom parsing for the collector |
| Playwright (Python) | `1.49.1` (workers/capture/requirements.txt) | Apache-2.0 | Library + browser binary | Human-operated capture session only; no session state or secrets in artifacts |
| FFmpeg | system package (`apt-get install ffmpeg` in the render compose service) | LGPL-2.1+ (GPL if built with GPL codecs) | Vendor binary | Our builds use stock Debian packages (LGPL). If a distribution later ships FFmpeg binaries, review codec/patent implications for that build before redistributing it. `FFMPEG_PATH` / `FFPROBE_PATH` override the binary. |
| PostgreSQL | `16-alpine` (infra/docker) | PostgreSQL License | Service (container) | Notice retention required |
| Redis | `7-alpine` (infra/docker) | RSALv2/SSPLv1 (server), MIT (clients) | Service (container) | Self-hosted use is fine; no redistribution of modified forks. Used as the API cache layer (v0.22). |
| redis-py | `5.2.1` (services/api/requirements.txt) | MIT | Library (optional) | The API imports it lazily; without it the cache layer is disabled and the system runs unchanged. |
| Pillow | `12.3.0` (workers/requirements.txt) | MIT-CMU (HPND) | Library | Render QC measures caption widths with the real font file (libass sizing rule); also produces PNG covers. Without it QC falls back to a labelled estimate. |
| tzdata | `2026.4` (services/api/requirements.txt) | Apache-2.0 (package), public-domain IANA data | Library | Supplies `zoneinfo` data where the OS has none (Windows); used for the YouTube Pacific quota day and schedule time zones. |
| MinIO (S3-compatible storage) | `RELEASE.2024-06-13T22-53-53Z` (pinned by release tag) | AGPL-3.0 | Service (container, optional profile) | Used unmodified as the local S3 endpoint in dev; production deployments can point `MTK_S3_*` at any S3-compatible store. |
| Next.js / React | apps/dashboard/package.json | MIT | Library | — |
| TypeScript | `^5.7.2` (root package.json) | Apache-2.0 | Library | — |
| zod | packages/offer-schema | MIT | Library | Offer schema shared with the dashboard |
| moto (test-only) | services/api tests | Apache-2.0 | Library (dev) | S3 mock used by the object-storage tests |

## Evaluated and NOT adopted (with the reason)

| Project | License | Decision |
|---|---|---|
| dgtlmoon/changedetection.io | Apache-2.0 | Not deployed. The needed capability (watch a page, diff it, feed the inbox) is implemented in-house as the `page_watch` collector adapter (`packages/source_adapters/page_watch.py`), which keeps the canonical-URL dedupe key inside our own API instead of a second app's storage. Re-evaluable per source; the plan permits it as a collector, never as validity proof. |
| n8n-io/n8n | Sustainable Use License (not OSI) | Not adopted. Our worker loops (collect → batch → render → publish → metrics → monitor) cover the orchestration without a license-restricted platform; n8n would add a deployment surface and a second source of truth for schedules. |
| activepieces/activepieces | per-component | Not adopted — same reasoning as n8n. |
| gitroomhq/postiz-app | AGPL-3.0 | Not integrated. Official platform adapters cover the publishing path with no AGPL network-use obligations; Postiz stays an explicitly optional option (runbook §9). |
| Remotion | Source-available; commercial pricing | Not adopted. FFmpeg presets (16:9 / 9:16 + burned captions + narration mix) cover the current render needs with no per-render licence cost. |
| huggingface/huggingface_hub | Apache-2.0 | Not adopted. Claim extraction is deterministic and evidence-linked (§3) — no model inference is required, so there is no provider pricing, quota, or model-licence exposure. |
| BullMQ | MIT | Not adopted. The job queue is the Postgres schedule table plus worker loops, which keeps the workers dependency-light (httpx only) and keeps every job state queryable in SQL. |
| cheahjs/free-llm-api-resources, mnfst/awesome-free-llm-apis, for-the-zero/Free-LLM-Collection | — | Reference only; never executed in the pipeline, never trusted as evidence (§2). |

## Rules

1. Pin exact versions of packages and images; never float a tag in production.
2. Re-read the LICENSE at the pinned version before any upgrade (licenses change).
3. Record every new upstream here **before** it enters the build.
4. Upgrade path: [`upgrade-checklist.md`](upgrade-checklist.md).
5. Dependency freshness is checked monthly by `.github/workflows/dependency-watch.yml`
   (read-only report; it never bumps a pin automatically).
