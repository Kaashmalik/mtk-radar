# Open-Source Integrations — Evaluation & Merge Strategy

Part of the MTK RADAR AI build plan. Companion document to the [master plan](../docs/master%20plan.md).

> **Rule of thumb:** Do NOT merge large external applications into this repository. Keep MTK RADAR AI in its own monorepo and integrate mature tools through **APIs or containers**, with pinned upstream versions. Fork only to maintain a necessary patch.

---

## 1. Integration strategy

### How we integrate (merge tiers)

| Tier | Meaning | Applies to |
|---|---|---|
| **Integrate** (container/service) | Run upstream project as-is in Docker, talk to it over its API or webhooks; no code enters our repo | changedetection.io, Postiz, n8n |
| **Library** (dependency) | Install as a pinned package dependency from a registry | huggingface_hub, BullMQ, Playwright client libs |
| **Vendor** (binary/tool) | Use as a build/runtime binary or desktop tool; not our source code | FFmpeg, Kdenlive |
| **Fork** (last resort) | Maintain a patch that upstream has not accepted; upstreamed as soon as possible | None today — create only when a required fix is blocked |
| **Reference only** | Use as lead lists / reading material; never executed in our pipeline | free-LLM-api community lists |

### Fork checklist (only if forced to fork)

1. Confirm the fix cannot be achieved via configuration, wrapper, or an upstream issue/PR.
2. Fork into our GitHub org, branch from the pinned release tag (not `main`).
3. Keep our patch as one or a few small commits; document the delta in `THIRD_PARTY_NOTICES`.
4. Add an automated check that rebases our patch onto each new upstream tag.
5. Upstream the patch; delete the fork when the next upstream release includes it.

### Before adopting ANY repository

- [ ] Read the actual `LICENSE` file at the version we pin (licenses change between releases).
- [ ] Check recent release activity (last release date, maintainers, commit volume).
- [ ] Scan open security advisories and CVE databases.
- [ ] Triage open issues for problems related to our intended use.
- [ ] Confirm deployment requirements (runtime, services, resources).
- [ ] Confirm the API surface we need actually exists and is documented.
- [ ] Record the decision (repo, version, license, integration tier) in `THIRD_PARTY_NOTICES`.
- [ ] Define the upgrade path: how updates are tested and merged.

---

## 2. Approved evaluation list

| Repository / project | Integration tier | Use in this product | License | Key caution |
|---|---|---|---|---|
| [dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io) | Integrate | Monitor official pages for visible changes and alert our collector workers | Confirm at pin time | Use as a collector — it is **not** proof an offer is valid; confirm page-access rules per target |
| [microsoft/playwright](https://github.com/microsoft/playwright) | Library (+AOT browser binaries) | Browser automation for the human-operated claim capture session | Apache-2.0 | Use isolated contexts; never store session state or secrets in artifacts |
| [n8n-io/n8n](https://github.com/n8n-io/n8n) | Integrate | Rapid prototyping of integrations and notification flows | Sustainable Use License (NOT standard OSI open source) | Verify use restrictions before embedding; treat as prototype tooling |
| [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | Integrate | Optional self-hosted publishing calendar and platform connectors | AGPL-3.0 | Assess network-use (AGPL) obligations, platform coverage, and compliance before hosting or modifying |
| [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | Vendor (binary) | Transcode, resize, mix audio, burn captions, create 16:9/9:16 derivatives | LGPL/GPL (build-dependent) | Check codec/patent implications of our exact build configuration |
| [KDE/kdenlive](https://kdenlive.org/) | Vendor (desktop tool) | Manual multi-track editing when the creator wants hands-on editing | GPL (desktop app) | Exchange files/asset bundles — do not assume seamless CapCut/Kdenlive project compatibility |
| [huggingface/huggingface_hub](https://github.com/huggingface/huggingface_hub) | Library | Read Hub model metadata and selected public model info | Apache-2.0 | A model on the Hub is **not** free to run — verify provider pricing, quota, license |
| PostgreSQL + Redis + BullMQ | Library / service | Durable offer database and job queue | PostgreSQL License / BSD / MIT | Set retention, backups, idempotency, and migration policy early |
| [Remotion](https://www.remotion.dev/docs/license/pricing) | Library (evaluate) | React-based templated video rendering | Source-available; commercial pricing varies | Review official license/pricing for OUR business use before adopting |
| [activepieces/activepieces](https://github.com/activepieces/activepieces) | Integrate (alternate) | Alternative workflow orchestration to n8n | Confirm per component | Component licenses may differ; check before deployment |
| cheahjs/free-llm-api-resources, mnfst/awesome-free-llm-apis, for-the-zero/Free-LLM-Collection | Reference only | Lead generators for candidate model/API offers | — | Never trusted sources. Diff repo updates → then verify pricing on the provider's official page |

---

## 3. Integration to-dos — CLOSED (decisions recorded)

- [x] `docs/third-party-notices.md` exists with the real pins, licenses and obligations.
- [x] compose entries for changedetection.io / Postiz / n8n — **decided: not added** (see the table in §2 of the notices file). The in-house `page_watch` collector adapter covers page monitoring, our own workers cover orchestration, and the platform adapters cover publishing — so no extra container, licence surface or second source of truth is introduced.
- [x] every upstream is pinned to an exact version (`fastapi==0.115.5`, `playwright==1.49.1`, `postgres:16-alpine`, `minio:RELEASE.2024-06-13T22-53-53Z`, …). Docker images are pinned by tag rather than digest — a digest pin per deployment is the next hardening step.
- [x] monthly freshness check: `.github/workflows/dependency-watch.yml` (read-only report, never edits a pin).
- [x] `docs/upgrade-checklist.md` (backup → staging → verify connectors → tag → promote → record).
- [x] n8n vs Activepieces — **neither**: the worker loops cover the orchestration without a licence-restricted platform.
- [x] Remotion licensing — **not adopted**: FFmpeg presets cover the render needs with no per-render licence cost.
- [x] Postiz AGPL — **not integrated**: official adapters mean no network-use obligations; it stays an explicitly optional option (runbook §9).

---

## 4. What we never do

- ❌ Copy a whole scheduler or workflow engine into the app before proving the integration route is insufficient.
- ❌ Merge upstream application source into this monorepo.
- ❌ Automate browser clicks to evade platform API rules (Playwright is for capture sessions only).
- ❌ Trust a community curated list as verification evidence.

---

*Last reviewed: October 2026 (v0.21) — every to-do above is closed with a recorded decision. Re-verify all licenses before each upgrade; see `third-party-notices.md` and `upgrade-checklist.md`.*
