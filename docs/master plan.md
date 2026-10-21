# MTK RADAR AI

Master build plan for trusted offer discovery, real claim walkthroughs, custom video editing, and scheduled multi-platform publishing.

Created by Muhammad Kashif by MTK Codex | October 2026

---

## Executive recommendation

Build a web dashboard with a small browser extension and a background workflow service. The dashboard is the source of truth for offers, evidence, video projects, edits, and scheduled posts. The extension lets you save a page or social post you are viewing; scheduled collectors discover updates without requiring the extension to stay open.

Start with verified source monitoring, a review queue, and a repeatable video package. Add capture and rendering next. Integrate platform publishing only after the content workflow works reliably. Treat each offer as time-sensitive data: eligibility, region, expiry, claim steps, and current terms must be rechecked immediately before recording and publishing.

## 1. Product scope and user journey

| Stage | What the platform does | Human control |
|---|---|---|
| Discover | Collect candidate changes from trusted source feeds, APIs, release notes, official pages, and saved links. | Choose source categories and regions. |
| Verify | Extract offer fields, preserve evidence, compare sources, and flag conflicts or missing terms. | Approve, reject, or request more evidence. |
| Prepare | Create a claim checklist, script, command cards, shot list, and platform copy. | Edit factual claims and narration. |
| Capture and edit | Record the real claim flow; generate captions, voiceover, intro/outro, and aspect-ratio exports. | Review redactions and edit in-app or external editor. |
| Schedule | Create a platform-specific post package, schedule it, and track status. | Final approval per platform; cancel or reschedule. |
| Learn | Record results and corrections; refresh or expire stale offer pages. | Correct errors and request takedown/update. |

## 2. What counts as a trustworthy source

Use a source registry, not a broad "scrape the internet" rule. Assign each source an owner, official domain/account identifier, collection method, reliability class, polling interval, and last-checked time. Social posts can be discovery signals; official terms pages and provider dashboards are stronger evidence for eligibility and redemption details.

Hugging Face is a useful example of why "free model" needs precision: its Inference Providers documentation describes pay-as-you-go service and monthly included credits for some paid plans. Treat every model/provider/plan combination separately, and do not label a model endpoint as free unless current official pricing confirms it. (Current docs: https://huggingface.co/docs/inference-providers/pricing)

| Category | Initial source list | How to use it |
|---|---|---|
| Model hubs and inference | Hugging Face Hub, official Inference Providers docs, provider model catalogs, official model release notes. | Track new model IDs, provider availability, pricing, included credits, rate limits, regions, and deprecation notices. |
| AI developer platforms | OpenAI, Anthropic, Google AI/Gemini, Mistral, Cohere, NVIDIA, Together, Fireworks, Groq, DeepInfra, Replicate, OpenRouter, Cloudflare Workers AI. | Watch official changelogs, pricing/credits pages, docs, newsletters, and provider status pages. Recheck model availability and quotas. |
| Open-source coding tools | OpenCode, Ollama, llama.cpp, vLLM, Hugging Face libraries, GitHub release feeds for selected repos. | Detect new free/local models, new integrations, license changes, and release instructions. |
| Student and community programs | GitHub Student Developer Pack, MLH programs/events/prizes, university partnerships, verified student benefit pages. | Separate education benefits, event swag/prizes, and actual credits; capture country, enrollment proof, deadline, and limits. |
| Cloud and startup programs | AWS Activate, Google for Startups/Cloud, Microsoft for Startups, Oracle, NVIDIA, and official accelerator partners. | Track eligibility carefully: many offers are application-based and not universal signup credits. |
| Domains and software perks | .TECH and other registrars, hosting vendors, IDEs, databases, design and productivity tools. | Record the exact promo code, redemption URL, renewal price, auto-renewal terms, exclusions, and expiration. |

## 3. Verification design

Keep immutable evidence snapshots: page URL, retrieval timestamp, publisher identity, text excerpt, and content hash. Store screenshots only when needed and redact personal details.

Use the LLM for structured extraction and comparison, never as the evidence source. Save each extracted field with the exact supporting source and confidence.

Require at least one official source for "verified." For high-impact claims such as money, eligibility, expiration, or redemption instructions, request two official sources when available or mark "single-source official confirmation."

Check that the source belongs to the provider (domain and account handle), the page is current, the offer has not expired, the country is supported, and the terms do not hide renewal/payment obligations.

Use states: Candidate → Evidence needed → Verified → Approved for video → Published → Expired/Corrected. Block video generation from Candidate or Evidence needed.

Keep a correction workflow. If terms change, pause scheduled posts, mark affected videos stale, and generate an update notice or replacement.

### Offer record schema

| Field | Example / rule |
|---|---|
| title / provider / category | "One-year .tech domain promotion"; Registrar; Domain offer |
| offer_type | Free trial, credits, student perk, model access, giveaway, discount, swag/prize |
| eligibility | Country, student/startup status, new-customer rule, verification required |
| value and limits | Currency, credit amount, usage cap, duration, excluded services |
| claim_steps | Ordered steps; mark commands, account actions, and manual checks |
| promo details | Code, official redemption link, start/end date, timezone |
| renewal and costs | Auto-renew status, regular renewal price, payment method requirement |
| evidence[] | Official URL, source type, captured date, supported fields, quote/snippet, hash |
| verification status | State, reviewer, reviewed_at, expiry/recheck time, conflict notes |
| content status | Script version, capture session, video versions, approvals, schedule, post IDs |

## 4. Realistic claim walkthrough production

The video should show a genuine end-to-end claim on your own eligible account, from one laptop screen, with clear narration and visible checkpoints. Do not stage a fake success screen or imply a universal result. If a real code or account cannot be shown publicly, use a clearly labeled demo account or blur sensitive areas while preserving the real steps.

Command safety rule: generate commands from official documentation, test them in a clean environment, show the exact expected output, and explain destructive or billable effects. Never put API keys, passwords, recovery codes, or personal account data in the recording, transcript, terminal history, or downloadable project. For a domain offer, demonstrate the real registrar flow and clearly show the ordinary renewal price and auto-renew setting before finalizing.

| Video section | Screen content | Narration / overlay |
|---|---|---|
| Hook and date | Offer name, provider, "checked on" date, country/eligibility label. | What the offer is and who should keep watching. |
| Before starting | Official offer and terms pages; highlight expiration, limits, renewal fees. | Who qualifies, what is included, and what is not. |
| Claim steps | Real browser navigation, form choices, promo code entry, confirmation page. | Explain each click; pause on irreversible or paid decisions. |
| Commands / setup | Terminal or editor visible only where required; copyable command cards. | State OS/shell, prerequisites, expected output, and what each command changes. |
| Verify the benefit | Provider account dashboard, product plan, model endpoint, or domain panel. | Show where to confirm activation, quota, expiry, or redemption status. |
| Wrap-up | Summary card with steps, eligibility, renewal warning, and official links. | Recap commands and steps; say that terms may change and link to sources. |

## 5. Video workspace and custom editing

Create a project folder per offer: evidence.json, script.md, source links, capture video, narration audio, captions (.srt/.vtt), thumbnail, rendered 16:9 and 9:16 files, and an edit manifest.

Provide "Open in CapCut" via clean exports and project assets; CapCut project format/integration may be limited, so do not promise round-trip editable timelines without testing. Also provide Kdenlive-friendly media and a project file where feasible.

Offer an in-dashboard trim/reorder/title/caption editor as a later feature. Use FFmpeg for deterministic exports; evaluate Remotion for templated React-driven rendering and check its licensing before commercial use.

Create versions: source capture, edited master, Shorts/Reels/TikTok cut, subtitles, and thumbnail. Preserve the project so you can revise it when the offer changes.

For authenticity, retain real screen recording and use AI for scripting, voice cleanup, captions, and graphics. Label synthetic narration/visuals where platform policy requires it.

## 6. Scheduled multi-platform publishing

The schedule belongs in the dashboard. Each video gets a content calendar entry with selected platforms, local publish time (Asia/Karachi by default), caption variant, thumbnail, privacy setting, approval state, and platform upload status. Use a queue with retries, idempotency keys, rate-limit handling, and a manual pause switch.

Postiz is a candidate to evaluate for self-hosted scheduling rather than a guaranteed universal publisher. Its repository is AGPL-3.0, so review obligations before embedding or modifying it. If you need tighter control, build a small publish adapter per official API and keep Postiz as an optional integration. Do not automate browser clicks to evade platform API rules.

| Platform | Publishing path | Plan around |
|---|---|---|
| YouTube | YouTube Data API upload or scheduler integration. | API project quota and channel OAuth; test visibility and metadata before production. |
| Facebook | Meta Graph API for eligible Pages/Reels or a supported scheduler. | Page permissions, app review/access levels, upload requirements, and account type. |
| Instagram | Instagram professional account publishing API or scheduler. | Professional account, connected identity, permissions, media processing, caption limits. |
| TikTok | Content Posting API or upload-for-review flow. | App approval and scopes; unaudited clients can be limited to private posts; creator confirmation may be needed. |
| Fallback | Export package and open platform's native upload screen. | Keep manual publishing available when APIs, review, or tokens block scheduling. |

## 7. Recommended architecture

| Layer | Recommended build | Notes |
|---|---|---|
| Dashboard | Next.js/React + TypeScript; responsive admin console. | Inbox, sources, evidence viewer, offer records, editor, calendar, analytics. |
| Browser extension | Manifest V3 extension with save-current-page action. | Capture URL/title/selected text and account handle; user confirms before sending. |
| API and workers | FastAPI (Python) or NestJS (TypeScript); background jobs using Redis + BullMQ or a durable workflow engine. | Separate collectors, verification, render, and publisher workers. |
| Database and storage | PostgreSQL; object storage for captures, assets, and renders. | Keep secrets in a vault/environment manager; signed URLs for assets. |
| Collectors | RSS/Atom, official APIs, GitHub releases, provider changelog pages; changedetection.io for selected pages. | Rate-limit, respect robots/terms, deduplicate, and log failures. |
| Browser capture | Playwright in isolated browser contexts. | Human-operated claim session; automate repeatable capture mechanics, not credential entry. |
| Video | FFmpeg + caption/transcript pipeline; optional Remotion templates. | Render reproducibly; maintain source assets and per-platform presets. |
| Approval and alerts | Dashboard review + optional Telegram/Discord notifications. | Buttons open the review record; approval is recorded with user/time/version. |
| Observability | Structured logs, job traces, dead-letter queue, source health dashboard. | Alert on stale sources, failed renders, expiring tokens, and failed posts. |

## 8. Open-source repositories to evaluate

Forking and merging approach: do not merge large external apps into one repository at the beginning. Keep your product in its own repo, integrate through APIs/containers, and pin upstream versions. Fork only when you need a maintained patch. Before adopting any repository, inspect the LICENSE, recent release activity, security advisories, open issues, deployment requirements, and whether it has the API you need. Maintain a THIRD_PARTY_NOTICES file and an upgrade checklist.

| Repository / project | Use in this product | Caution / integration choice |
|---|---|---|
| dgtlmoon/changedetection.io | Monitor official pages for visible changes and alert workers. | Use as a collector, not as proof that an offer is valid; confirm license and page access rules. |
| microsoft/playwright | Reliable browser automation and screen recording. | Use controlled contexts; avoid storing session state or secrets in artifacts. |
| n8n-io/n8n | Prototype integrations and alerts quickly. | Public source uses Sustainable Use License, not a standard OSI open-source license; check use restrictions. |
| gitroomhq/postiz-app | Self-hosted publishing calendar and platform connectors. | AGPL-3.0; assess network-use obligations and per-platform approval/coverage. |
| FFmpeg/FFmpeg | Transcode, resize, mix audio, burn captions, create derivatives. | Check codec/patent implications for your distribution and build settings. |
| Kdenlive/kdenlive | Manual multi-track editing for the creator. | Desktop editing app; exchange files/assets rather than assume seamless CapCut project compatibility. |
| huggingface/huggingface_hub | Read Hub model metadata and selected public model information. | Model availability does not mean free inference; validate provider pricing and model license. |
| PostgreSQL / Redis / BullMQ | Own the durable offer database and job queue. | Set retention, backups, idempotency, and migration policy early. |
| Remotion | React-based templated video rendering. | Licensing varies by company/product use; review official license/pricing before adoption. |

## 9. Delivery roadmap

| Phase | Build | Exit criteria |
|---|---|---|
| 0. Foundation | Source registry, offer schema, user roles, audit trail, project repo, deployment plan. | Can add/disable sources and explain every field in an offer. |
| 1. Offer radar | RSS, GitHub releases, selected official pages, extension save-link action, deduplication, inbox. | Candidate appears once with source/time and is reviewable. |
| 2. Verification desk | Structured extraction, official-source checks, evidence snapshots, conflict/staleness rules. | No unverified offer can enter script generation. |
| 3. Script and checklist | Claim guide, command card, factual citations, review and versioning. | Reviewer can trace every factual claim to evidence. |
| 4. Capture and video | Playwright screen recording, privacy redaction, captions, voice, FFmpeg templates, 16:9/9:16 exports. | One complete end-to-end video package is reproducible. |
| 5. Editing and schedule | Asset download, Kdenlive/CapCut handoff, calendar, platform-specific metadata, approval gates. | Schedule can pause, retry safely, and export manually. |
| 6. Publishing integrations | YouTube, Meta, TikTok and optional Postiz connections. | Each connector passes private/test posting and token-expiry recovery. |
| 7. Analytics and scale | Views, retention, clicks, corrections, source freshness, content performance. | Use data to prioritize topics and improve packaging, not to weaken verification. |

## 10. Core tables and API concepts

- **Sources:** provider, canonical domain/account, category, adapter, enabled, polling cadence, country scope, trust tier.
- **Items:** source item ID, URL, title, published/observed timestamps, normalized text hash, duplicate group.
- **Offers:** value, eligibility, limits, expiry, claim steps, status, confidence, recheck_at, correction state.
- **Evidence:** offer_id, source_id, captured content, exact supported fields, capture time, hash, reviewer.
- **Projects:** script versions, command cards, capture sessions, assets, render versions, disclosure metadata.
- **Approvals and schedules:** approver, approved version hash, platforms, local time, retry state, remote post IDs, outcome.

## 11. Quality, safety, and business rules

- Never call a promotion universal unless the provider says it is universal. State region and student/startup requirements in the opening and end summary.
- Clearly separate monetary credits from free model weights, free tiers, trial access, and contest prizes. Mention usage caps and whether a payment method is required.
- Recheck offers before recording and again before scheduled publication. If a deal expires or changes, pause queued posts automatically.
- Do not display or store API keys or redemption tokens in public footage. If the promo code is public, verify it is authorized for redistribution.
- Keep human approval before publishing, and allow editing/cancellation after scheduling. Never create accounts at scale or bypass eligibility checks.
- Keep a source correction link and version date in video descriptions. Make takedown/correction handling part of the workflow, not an afterthought.

## 12. Initial repo layout

```
apps/dashboard/
apps/extension/
services/api/
workers/collectors/
workers/verification/
workers/video/
workers/publishing/
packages/source_adapters/                     
packages/offer-schema/
packages/video-templates/
infra/docker/
docs/source-registry.md
docs/security-and-redaction.md
docs/third-party-notices.md
```

## 13. First practical build target

Build one complete case study before expanding sources: a current, officially documented developer/student offer with explicit eligibility. Collect the official announcement and terms, approve the offer record, create a script and checklist, capture a real browser walkthrough, produce landscape and vertical exports, edit the assets, and schedule a private/unlisted test. Measure time spent, missed details, corrections, and rendering reliability. Then add more source adapters.

## 14. Source tiers and collection policy

Use public APIs, RSS/Atom feeds, GitHub release feeds, official changelogs, official newsletters, and permitted page-change monitoring first. X, Reddit, Hacker News, Discord, and Telegram are discovery channels unless their posts are official and the offer terms are verified elsewhere. Respect each site's terms and rate limits; never build the source system around scraping private or logged-in content.

| Tier | Examples | What the system may conclude |
|---|---|---|
| A: provider-owned | Official AI lab blogs, pricing pages, docs, status pages, model catalogs, GitHub releases from the maintainer, GitHub Education, official MLH pages, registrar partner terms. | Can establish that a provider announced an offer; still verify exact eligibility, limits, dates, regions, and redemption outcome. |
| B: discovery leads | X posts, Reddit, Hacker News, community Discord/Telegram announcements, curated free-model lists. | May create a candidate record and source lead; cannot alone establish offer validity. |
| C: exclude pending proof | Coupon aggregators, unknown link shorteners, influencer claims without evidence, leaked codes. | Do not generate a claim guide or video until official confirmation is found. |

## 15. Offers catalog and example claim video

Catalog offers as distinct types: free/open-weight models, hosted inference free tiers, API trial credits, first-signup credits, cloud credits, student packs, hackathon prizes or swag, startup programs, software subscriptions, and domain/hosting discounts. Track whether each is free for everyone, application-based, student-only, time-limited, or a discount that renews at a paid rate.

Example pilot: a .TECH domain offer through a student-benefit program. Before producing it, verify the provider's live partner page, the student-program listing, the user's eligibility, the promo code and registration steps, the redemption deadline, and the normal renewal price/auto-renew setting. Record a genuine claim from a clean laptop profile only if the person on camera qualifies. If not eligible, make an explainer using a clearly labeled demo or a consenting eligible participant; never simulate a successful redemption.

Claim-video sequence: show the date and eligibility; open the official benefit page; open the terms; perform the claim in real time; show the confirmation and where the benefit appears in the account; explain any DNS or setup commands separately; finish with a summary card listing steps, commands, expiry, ongoing costs, and source links. Commands must be relevant to setup after the claim, tested for the stated shell/OS, and shown with expected output. Do not imply that deployment commands are part of redeeming a domain unless the provider's actual flow says so.

## 16. Build stack and external repository shortlist

Fastest practical build: React/TypeScript dashboard and Manifest V3 save-link extension; Supabase/Postgres for accounts, offers, evidence, review state, and schedules; n8n for early integrations and notifications; Python workers for parsing, verification, media redaction, and rendering; Playwright for a controlled real-screen recording workflow; FFmpeg for exports; Postiz as an optional publishing system. Keep the application's source of truth and core business rules in your own repository.

| Repository | Use | Adoption check |
|---|---|---|
| dgtlmoon/changedetection.io | Watch selected official pages for changes and notify the collector. | Confirm supported fetcher, page rules, current license, and permissions for each target. |
| n8n-io/n8n or activepieces/activepieces | Workflow orchestration and integrations. | Review the exact current license and deployment terms; n8n uses a Sustainable Use License, while Activepieces components may have distinct licenses. |
| gitroomhq/postiz-app | Optional publishing calendar and supported social integrations. | AGPL-3.0 repository; verify platform coverage, deployment dependencies, scopes, and compliance before hosting or modifying. |
| microsoft/playwright | Browser automation and video capture for a human-operated claim session. | Use isolated contexts; redact and inspect captures before they enter the media pipeline. |
| FFmpeg/FFmpeg and KDE/kdenlive | Programmatic transcodes and manual timeline editing. | Review build configuration and project interoperability; export an asset bundle for CapCut/Resolve rather than promise direct project compatibility. |
| cheahjs/free-llm-api-resources; mnfst/awesome-free-llm-apis; for-the-zero/Free-LLM-Collection | Community lists that can reveal candidate model/API offers. | Treat as lead generators only. Diff repo updates, then verify pricing and availability on the model provider's official page. |
| huggingface/huggingface_hub | Model metadata and Hub discovery. | A model on the Hub is not necessarily free to run; verify inference provider, model license, price, quota, and terms. |
| Remotion | React-based video template rendering. | Review current license/pricing for the project's actual business use before adopting. |

Fork strategy: keep MTK RADAR AI in its own monorepo; integrate mature tools over APIs or containers. Fork only to maintain a necessary patch. Pin versions, scan security advisories, record licenses in THIRD_PARTY_NOTICES, and define how upstream updates are tested and merged. Avoid copying a whole scheduler or workflow engine into your app before proving the integration route is insufficient.

## 17. Scheduling and publishing operations

Build a content calendar with per-platform schedules and Asia/Karachi as the default display timezone. Each queued post must reference an approved video version and offer evidence snapshot. Configure publish windows in settings; begin with a manageable cadence, then tune by audience analytics. Do not promise fixed "best hours" as universal. Schedule retries with idempotency keys, backoff, token-expiry alerts, and an operator-visible pause/cancel control. Recheck offer validity before upload and again before publish; automatically pause affected posts if the offer expires or changes.

| Queue state | Required condition | System action |
|---|---|---|
| Draft | Video assets exist. | Build captions, thumbnail, links, disclosures, and platform previews. |
| Needs approval | Factual and media checks complete. | Show claim evidence, eligibility, expiry, renewal terms, and redaction status. |
| Approved | A reviewer approved this exact version hash. | Allow schedule creation; reapproval required after material edits. |
| Scheduled | Platform and local timestamp selected. | Revalidate offer, check token, upload or hand off, and monitor status. |
| Published / failed / paused | Remote post ID or failure details recorded. | Store the result, retry eligible failures, or pause for human correction. |

## 18. Twelve-week implementation sequence

| Weeks | Deliverable | Done when |
|---|---|---|
| 1 | Repo foundation, Docker Compose/dev environment, database schema, source registry, secrets and audit model. | Local system starts; source and offer records can be created and reviewed. |
| 2 | RSS/Atom, GitHub release feeds, selected official-page monitoring, browser extension save-link action. | A candidate appears once with canonical URL, timestamp, and deduplication key. |
| 3-4 | Structured extraction, provider-domain allowlist, evidence snapshots, conflict/stale detection, reviewer queue. | Every verified field links to evidence; unverified records cannot enter script generation. |
| 5-6 | Claim checklist, real browser recording workflow, step log, redaction review, first offer recipe. | One eligible claim can be recorded and reviewed without leaking secrets. |
| 7-8 | Script and command cards, TTS option, captions, FFmpeg/Remotion templates, landscape/vertical exports. | A full video project can be regenerated from versioned source assets. |
| 9 | Editing handoff, project bundle, calendar, approval/version controls. | A creator can make edits and schedule a test post with rollback/pause. |
| 10 | Connect YouTube and one additional platform through official APIs or Postiz. | A private/test upload and token-expiry recovery are verified. |
| 11 | Add remaining platform connectors as permissions allow; expiry monitor and corrections. | Posts pause when an offer expires; corrections link to affected videos. |
| 12 | Analytics, backup/restore, docs, deployment hardening, first production review. | Operational runbook and source/credential recovery are documented. |

## 19. Recommended first release

Do the first ten videos with a partly manual workflow. That will expose where eligibility checks, recording, editing, captions, and posting actually consume time. The first software release should automate reliable detection, evidence capture, deduplication, review, and project packaging. Add scheduled publishing only after the content can be paused safely and corrected quickly. Growth depends on useful offers and strong explanations; a high-volume pipeline alone does not guarantee reach.

## Reference links checked for this plan

- Hugging Face Inference Providers pricing: https://huggingface.co/docs/inference-providers/pricing
- Hugging Face Inference Providers overview: https://huggingface.co/docs/inference-providers/index
- MLH official site and programs: https://mlh.io/
- GitHub REST API releases: https://docs.github.com/en/rest/releases
- changedetection.io repository: https://github.com/dgtlmoon/changedetection.io
- n8n Sustainable Use License documentation: https://docs.n8n.io/n8n-community-license/
- Postiz repository: https://github.com/gitroomhq/postiz-app
- YouTube videos.insert: https://developers.google.com/youtube/v3/docs/videos/insert
- TikTok Content Posting API: https://developers.tiktok.com/products/content-posting-api/
- Instagram API publishing overview: https://www.postman.com/meta/instagram/documentation/23987686-9386f468-7714-490f-9bfc-9442db5c8f00
- Kdenlive: https://kdenlive.org/
- Remotion license and pricing: https://www.remotion.dev/docs/license/pricing

> Current program terms, social-platform access, and repository licensing can change. Use this plan as the build blueprint; verify each live offer and integration at implementation time.
