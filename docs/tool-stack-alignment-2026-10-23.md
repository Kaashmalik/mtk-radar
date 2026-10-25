# External Tool-Stack Alignment — 2026-10-23

**Purpose:** Evaluate the published "best tool stack" for AI-offer content pipelines
(Perkstack, Find AI Credits, OBS Studio, Descript, CapCut Pro, Opus Clip Pro,
Metricool, Loomly, Buffer, Sprout Social, Hootsuite, Runway, HeyGen) against
MTK RADAR's in-house pipeline, and record which tools are adopted, which are
optional assists, and which are deliberately not adopted — with the same rigor
used for open-source upstreams in [`third-party-notices.md`](third-party-notices.md).

**Status: PROPOSED (reviewed 2026-10-25).** The adopt/skip entries are
recommendations, not shipped integrations. Present-tense capability statements
were checked against `0d3b043`; where the in-house pipeline is narrower than
this analysis first suggested, the text now says so.

**Rule applied:** the platform of record stays in this repository. No external
SaaS may become a second source of truth for evidence, approvals, schedules,
or published state. This is the same reasoning that rejected n8n and Postiz
(see `third-party-notices.md`, "Evaluated and NOT adopted").

## Pipeline map

| Stage | External stack pick | MTK RADAR equivalent | Decision |
|---|---|---|---|
| Discover | Perkstack, Find AI Credits | Source registry + RSS/GitHub/page-watch collectors + save-page extension | **Proposed: adopt as Tier-C discovery-only sources** (not registered or seeded yet) |
| Capture | OBS Studio | `workers/capture` (Playwright, human-operated) | **Proposed: optional complement** — no external-capture intake exists yet |
| Edit | Descript, CapCut Pro | `workers/render` + `workers/render/handoff.py` asset bundle | **Optional assist — at most one subscription** |
| Clipping | Opus Clip Pro | Same-timeline 9:16 renders with portrait-aware layout | **Not adopted** |
| Schedule & publish | Metricool (alt: Buffer, Sprout Social, Hootsuite) | Official platform APIs + schedule state machine + publishing workers | **Not adopted** |
| Approval workflow | Loomly | In-app approval gates (script-hash-bound, policy-checked) | **Not adopted** |
| Extras | Runway, HeyGen | FFmpeg render pipeline + TTS narration | **Optional, budget-gated, must obey disclosure rules** |

## Per-tool analysis

### Perkstack / Find AI Credits — adopt as discovery-only sources

These are coupon/aggregator-style discovery sites. Under the trust-tier policy
(`README.md` §Key Principles, `docs/source-registry.md`), aggregators are
**Tier C: excluded as evidence** until official confirmation exists. They are
legitimate *leads*: add them to the source registry as Tier C so candidates
found there enter the review inbox like any other lead, then get verified
against the provider's own terms pages.

- Register as Tier C, `manual_only` or `page_watch` collection — no scraping
  beyond permitted use, respect robots/ToS.
- Never auto-follow leaked coupon instructions (master plan §6 attribution rule).
- Store the discovery platform and the benefit provider separately in the UI.
- Cost: $0 (free tiers). Slight recurring-fetch cost only.

### OBS Studio — optional external capture complement

`workers/capture` records the claim flow through a controlled Playwright
session (isolation, redaction review, step log). OBS adds value where
Playwright cannot reach: system audio, terminal windows outside the browser,
native desktop apps, multi-monitor setups, and mobile screens.

Best practices if used:

- OBS recordings would enter the pipeline as **external capture media** — they
  must pass the same redaction review, provenance record, and freshness checks
  as Playwright captures before they can be attached to a project. This intake
  is **not implemented**; it is part of the proposal.
- Use OBS only for the *operator's own* consented account walkthroughs; all
  login/payment/identity actions remain human-controlled.
- OBS can double as the fix for audit gap **A11** only if a premium render
  needs more than the current capture: Playwright already records native
  1920×1080, so the old "capture is 1280×720" premise is stale.
- Cost: $0 (free, open source).

### Descript / CapCut Pro — optional manual polish, pick at most one

`workers/render` already produces captions, narration, and 16:9/9:16 exports;
`handoff.py` exports an asset bundle (renders, captions, script, evidence,
manifest) for external editors; it is not a native project file and does not
include project-root extras. The master
plan explicitly warns: do not promise round-trip editable CapCut/Kdenlive
timelines from a ZIP of assets (master plan §9 / WP10), and an OpenTimelineIO
interchange is only worth adding after verifying export/import on a target
editor version.

If either tool is subscribed to:

- Use it **after** the QC-passed export, for optional hands-on polish only.
- Any re-imported cut is *new unapproved media*: it needs provenance, fresh
  render QC, and a new package approval before scheduling (master plan §9).
- A Descript-transcript edit never silently changes factual claims; claim
  wording changes must flow back through script revision + approval.
- Do not pay for both. Choose one (Descript suits narration-heavy long-form;
  CapCut suits fast short-form captioning — the render worker already covers
  the short-form baseline).
- Cost: ~$15–24/month — the only recurring subscription this analysis justifies.

### Opus Clip Pro — not adopted

The render worker produces 9:16 variants from the *same approved timeline*.
The current layout is a **blurred background with the full frame fitted inside**
(`force_original_aspect_ratio=decrease`); it does **not** magnify or track an
active region. Opus Clip re-cuts long video into clips, but its output:

- has no claim/evidence linkage (clips cannot cite snapshots),
- breaks the versioning invariant (approval binds script + timeline + render
  bytes; an Opus re-cut is none of those),
- needs full re-approval as new media anyway.

For the current volume, the in-house portrait renders cover the need.
Re-evaluate only if long-form repurposing at scale becomes a measured need —
and then treat clips as unapproved drafts.

### Metricool / Buffer / Sprout Social / Hootsuite — not adopted

Publishing stays in-house through official platform APIs (YouTube Data, Meta
Graph, Instagram Graph, TikTok Content Posting) because the scheduler must
enforce guarantees no third-party tool models:

- **Expiry auto-pause** — queued posts pause when offer terms change or the
  offer expires; external schedulers have no concept of offer state.
- **Correction propagation** — published descriptions get correction notices
  written back; a third-party scheduler breaks that write-back path.
- **Reconciliation** — "published" means remote visibility confirmed, with a
  held state (`outcome_detail.hold` + `reconcile_outcome`) for ambiguous
  outcomes; there is no `reconciliation_required` literal in the state machine.
  External dashboards hide this state machine.
- **Per-account credential binding** (A18) and server-side policy re-checks
  on every gated write.

A second scheduler is a second source of truth for schedules — the exact
reason n8n and Postiz were rejected. One legitimate narrow use: *read-only*
metrics ingestion, but the in-house metrics worker already covers platform
Analytics APIs.

Record in `third-party-notices.md` alongside Postiz if we ever revisit this.

### Loomly — not adopted

Approval stays in-app by design. An MTK RADAR approval binds **all** release
inputs: fact pack, script, timeline, footage, redactions, narration, captions,
thumbnail, metadata, render bytes, target account, and policy version
(master plan §4 versioning invariant). Loomly's approval workflow cannot bind
script hashes — adopting it would produce approvals detached from content
versions, which is strictly weaker than the existing gate. The automation
policy (`docs/automation-and-human-control.md`) already provides the
manual/assisted/autopilot control Loomly is being recommended for.

### Runway / HeyGen — optional, budget-gated, disclosure-required

- **Runway** (AI video generation): acceptable only for abstract B-roll,
  covers, and motion graphics. It must never generate fake UI, fake
  dashboards, or implied claim results — master plan §8 forbids AI
  enhancement that invents UI text or changes evidence. Synthetic visuals
  are labeled where platform policy requires.
- **HeyGen** (AI avatars): competes with the existing TTS narration path.
  Only permitted with a licensed/consented voice and the synthetic-media
  disclosure per platform rules. Not needed while the TTS pipeline works.

Neither affects the publishing gates; both are budget items, not platform items.

## Cost comparison

| Stack | Monthly | mtk-radar equivalent | Monthly |
|---|---|---|---|
| Solo tier (Descript + CapCut + Metricool + free discovery + OBS) | ~$30–60 | mtk-radar (self-hosted) + OBS | **~$0** infra; + optional $15–24 editor |
| Team tier (adds Opus Clip + Loomly; Sprout/Hootsuite for listening) | ~$100–250 | Nothing to add — in-house covers it | **$0** |

The published stack costs $30–250/month because external tools cannot share
state, so creators buy several half-connected subscriptions. mtk-radar keeps
evidence, approval, scheduling, and publishing in one state machine — that is
the structural reason the subscriptions are unnecessary here.

## Decisions

| Tool | Decision | Conditions under which to revisit |
|---|---|---|
| Perkstack, Find AI Credits | Proposed Tier-C discovery sources (not implemented) | Only if their ToS/API permits automated collection; else operator-saved links |
| OBS Studio | Proposed optional external-capture intake (not implemented) | Recordings would pass the same redaction/provenance gates as Playwright captures |
| Descript or CapCut Pro (one) | Optional | Editor output is unapproved media until provenance + QC + re-approval |
| Opus Clip Pro | Not adopted | Long-form repurposing at measured scale; clips treated as unapproved drafts |
| Metricool / Buffer / Sprout / Hootsuite | Not adopted | Never as scheduler; read-only analytics ingestion only if metrics worker gaps appear |
| Loomly | Not adopted | Only if team size (3+ approvers) exceeds the in-app review model — and even then as notification layer, not approval authority |
| Runway / HeyGen | Optional extras | Synthetic visuals must not invent UI; voices licensed; disclosures applied |

## Review policy

Re-check this analysis when (a) any stack tool's pricing/coverage changes
materially, (b) WP10 (light in-app editing) ships and removes the editor
subscription need, or (c) publishing volume justifies re-evaluating clipping.
Record any change here and in `third-party-notices.md` if a dependency enters
the build.
