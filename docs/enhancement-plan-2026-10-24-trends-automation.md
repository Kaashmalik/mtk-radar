# Enhancement plan — Trend Radar v2, research-to-video pipeline, one-click publishing, and a cost engine (24 October 2026)

**Plan date:** 24 October 2026 (UTC)
**Baseline commit:** `89f4e9d` — *fix: dashboard review follow-up… (v0.30 line)*
**Method:** full read-only code audit (API, workers, dashboard, packages, docs) + live
web research on 2026 trend/hashtag/LLM-cost landscape. This is a plan, **not** a
production-readiness certificate and not a promise of views or revenue.

**Related plans (this doc extends, does not replace):**
- [enhancement-plan-2026-10-22.md](enhancement-plan-2026-10-22.md) — security/dashboard/jobs hardening (mostly implemented)
- [system-review-2026-10-23.md](system-review-2026-10-23.md) — day-4/5 dispositions and the deferred P2/P3 table
- [automation-master-plan-2026-10-21.md](automation-master-plan-2026-10-21.md) — WP05/WP06 trend radar (still unchecked there)

---

## 1. Executive summary

The system today is a **strong, honest pipeline that still needs a human hand on
every stage**: the trend radar must be clicked to scan, scored topics dead-end at
`shortlisted` because they can never be promoted, hashtags come from hard-coded
dictionaries, and nothing in the schema knows what anything costs.

This plan closes four product promises:

| Goal | Today | Target |
|---|---|---|
| **Hot-topic discovery with evidence** | Radar scores keyword matches on official-page diffs; zero external trend sources; scan is a manual button | Multi-source trend ingestion (Google Trends, GitHub star velocity, HN, arXiv/HF Daily Papers, YouTube search velocity) → scored **with evidence links** → auto re-scoring on a cadence, not one-shot |
| **Research → best/trending video list** | Two unrelated lists: radar (scored, dead-ends) and render queue (unscored) | One **Production Queue**: ranked "videos to make" = trend momentum × evidence strength × freshness × feasibility; one-click promote to offer |
| **One-click schedule & post** | Per-row calendar approve; per-offer×platform schedule create; static hashtags | **Batch approve/schedule**, "schedule all platforms for this video" in one click, per-platform **evidence-based hashtag generation** (trending-source aware, 3–5 tags, platform-correct limits) |
| **Cost-effective & robust** | Optional LLM/TTS with zero accounting, zero caching, no local-model path; Meta/TikTok tokens unmanaged; no rate-limit handling | **Cost engine** (usage ledger, budgets, hash-keyed caches, Kokoro TTS, Ollama option), token lifecycle automation, platform rate-limit backoff |

Everything stays inside the existing safety envelope: autopilot remains
policy-gated, human gates (redaction, playback review, evidence) are untouched,
and every new automation is a policy-controlled stage that defaults to **Assisted**.

**Priority order:** trend ingestion + production queue (the product's core
promise) → one-click scheduling/publishing UX → cost engine → robustness →
calendar polish.

---

## 2. What already exists (preserve it — do not rebuild)

Verified by code read on 24 October 2026:

- **Pipeline spine:** collectors → items (canonical-URL dedup, migration 031) →
  verification (snapshot-bound evidence, official-domain checks) → scriptgen →
  capture (human) → render + QC → schedules (pinned hashes) → publishing
  (fail-closed release gate, resumable uploads, confirm-before-published).
- **Durable job queue** (`services/api/jobs_api.py`): SKIP LOCKED leases, dedupe
  keys, dead-letter, operator retry; collect/render/publish all queue-driven.
- **Trend engine core** (`services/api/trend_engine.py`): 6 transparent scores,
  radar bands, 3-competitor rule — deterministic, honest about heuristics.
- **SEO plumbing** (`services/api/seo.py`): YouTube titles ≤50 chars, 5–8 plain
  tags, thumbnail text ≤3 words, release-gate enforcement of all of it.
- **Automation policy** (`services/api/automation.py`): manual/assisted/autopilot,
  per-op kill switch re-check, daily budgets, preflight.
- **Robustness pockets:** exponential retry, upload holds, token-refresh hook for
  YouTube, heartbeats, Prometheus, per-IP auth limiter, graceful SIGTERM.

---

## 3. Gap findings (audited, ranked by impact)

| # | Gap | Evidence | Impact |
|---|-----|----------|--------|
| 1 | **No automated trend ingestion** — only RSS / GitHub releases / page-watch on 10 seeded Tier-A sources; no Google Trends / GitHub stars / HN / arXiv / HF papers / YouTube velocity collectors | `packages/source_adapters/` (3 adapters only); `seed_sources.py` (10 sources) | The radar scores a trickle of page diffs; "hot topics" never arrive |
| 2 | **Radar dead-ends**: `promoted` status defined but no endpoint sets it; no trend→offer path; render queue ignores scores | `trends_api.py:33` (`TrendStatusIn`), `offers_api.py` (only `from-item`), `RadarActions.tsx:17` | Scored topics require manual re-finding in the inbox; end-to-end automation impossible |
| 3 | **`/trends/scan` is a manual, one-shot button**; items marked processed once, never re-scored as momentum develops | `trends_api.py:192-198` (sets `processed=TRUE`), only caller `RadarActions.tsx:17` | Radar is stale within hours; "trending" cannot exist without time-series |
| 4 | **No trend-score history → no velocity/Δ math** | `trend_engine.py` recomputes destructively; no history table | Freshness decay exists; momentum (the trend signal) does not |
| 5 | **Zero cost accounting or budgets** — no LLM/TTS usage rows, no spend caps, `.env.example` documents no `VERIFY_LLM_*`/`TTS_*` knobs | grep: no `llm_usage`/`usage` tables; `extractors.py:215-263` | Autopilot + a billing key = unbounded, invisible spend |
| 6 | **No LLM/TTS caching** — LLM called once per document *section* per round; TTS re-synthesizes identical narration every re-render | `extractors.py:300-353` (`extract_document` loop), `narration.py:117-132` (`synthesize_all`) | Direct, recurring money waste |
| 7 | **Static hashtags** from hard-coded pools; IG/TikTok get them in caption, YouTube description never gets a hashtag line, Facebook gets none (its limit is 0 but tags are still appended upstream); no trending-tag source, no metrics feedback | `seo.py:33-42` (`_DEFAULT_HASHTAGS`), `seo.py:394`, `platforms/youtube.py:197` | Discoverability ceiling; the "trending hashtags" ask is unimplemented |
| 8 | **No local-model path** — Ollama/llama.cpp exist in docs only; no provider adapter or capability probe | `extractors.py` (OpenAI-compatible env as the only lever) | No cost ceiling or privacy option despite the repo *watching* Ollama releases |
| 9 | **No batch operator actions** — per-row calendar approve; schedules created one offer×platform at a time | `ScheduleActions.tsx:38-91`, `ScheduleForm.tsx` | Assisted mode = dozens of clicks per video per week |
| 10 | **No unified ranked production queue** combining trend score, evidence strength, freshness, render readiness | `renders_api.py:399-517` (ordered by capture date, not score) | Operator can't see "what to record next" in one list |
| 11 | **Meta/Instagram/TikTok token lifecycle unmanaged** — only YouTube refreshes programmatically; IG tokens die ~60 days | `platforms/youtube.py:145-173` (has `on_refresh`); adapters for IG/FB/TikTok: none | Publishing silently stalls until a monitor alert someone must notice |
| 12 | **No per-platform rate-limit handling** — `Retry-After`/quota headers unparsed; only the daily schedule budget exists | `platforms/base.py`, `publishing/main.py:556-601` | 429/403 storms mark posts failed or hammer provider APIs |
| 13 | **No media retention/GC** — 90-day retention is a doc assumption; `media_backup` copies, never prunes | grep `media_backup` | Storage creep on R2/local |
| 14 | **Redis nearly idle** — one 30-second dashboard cache; no caching of extraction, trend scans, trend fetches | `services/api/cache.py:28-29` | Free infra idles while every fetch/LLM call re-pays |
| 15 | **No on-demand "run the pipeline now"** — `/automation/start` only arms policy; work waits on worker sweeps; capture has no batch-prep queue | `automation_api.py`, `batch/main.py` | The "one-click" experience lacks its button |

**Honorable mentions:** LLM call is single-shot with silent `None` on failure
(no retry/backoff); notification cooldown is in-memory (lost on restart); expired
leases recoverable only one-by-one; collector sweep cadence state in-memory
(`collectors/main.py:123`); growth feedback loop (metrics → topic/tag choice) not
closed despite `growth_engine.recommendations()` existing.

---

## 4. External research — what 2026 actually allows (with sources)

These facts constrain the design. Re-verify at implementation time; providers change.

### 4.1 Trend data sources

| Source | 2026 status | Verdict for us |
|---|---|---|
| **Google Trends** | Official API announced 24 Jul 2025 but **alpha, application-gated**. `pytrends` archived Apr 2025 (trending-search endpoints 404 as of Sep 2026). Maintained fork: **`trendspyg`** (trending-now, interest-over-time, related queries). Google's data lags ~48 h | Adopt `trendspyg`-style adapter behind a **tolerant wrapper** (treat as Tier-B lead signal only; never evidence). Sources: [scrapfly](https://scrapfly.io/blog/posts/google-trends-api-alternatives), [scrapebadger](https://scrapebadger.com/blog/does-google-trends-have-an-api-what-to-use-in-2026) |
| **Hugging Face Daily Papers** | **Free JSON API**: `GET /api/daily_papers?sort=trending&date=YYYY-MM-DD` (limit, week, month params). Direct arXiv IDs | **First-class adapter.** Perfect "hot research with evidence" feed — the paper page *is* the evidence link, upvotes are the momentum signal |
| **GitHub** | REST free at 5,000 req/h (token); Releases API already integrated; **star velocity** computed from `stargazers` sampling or Search API | Add star-velocity adapter (Δstars/day per watched repo) — feeds existing github-releases items |
| **Hacker News** | **Free, no-key Algolia API** (`hn.algolia.com/api/v1/search_by_date?query=...&numericFilters=points>N`); Firebase API for items | Point-velocity adapter for AI/dev keywords (tiered akin to existing X/Reddit treatment) |
| **YouTube trending/velocity** | Data API free but **quota-shaped: 10,000 units/day; `search.list` = 100 units, max 100 calls/day**; `videos.list` = 1 unit | Budgeted, cached keyword-velocity probes (e.g. 20 long-interval keywords/day); **never** scrape. Dec 2025 revision: `videos.insert` now ~100-from-100/day bucket — publishing is cheap, research is the scarce quota |
| **TikTok** | Creative Center scraping now **prohibited** (Apr 2026 transparency rules); sanctioned bulk path = gated Research API. Third-party paid APIs exist (TickerTrends, Apify, EnsembleData) | **Do not scrape.** Manual Creative Center entry maps to the existing 3-competitor typed-evidence flow; optional paid API behind a setting later |
| **Reddit** | Free API heavily limited / paid tiers; RSS still readable for public subs | Keep as lead-signal RSS only (consistent with existing Tier-C policy) |

Sources: [YouTube quota calculator](https://developers.google.com/youtube/data/determine_quota_cost), [Blotato API pricing](https://www.blotato.com/blog/youtube-api-pricing), [TikTok Creative Center guide](https://www.admapix.com/blog/ad-intelligence/tiktok-creative-center-tutorial), [HF papers skill docs](https://mcpservers.org/agent-skills/huggingface/huggingface-papers).

### 4.2 Hashtag reality (do it right, not more)

- **Effective counts:** YouTube 3–5 hashtags (60 hard cap; >60 suppresses search), only 3 show above the title; TikTok 3–5; Instagram 3–5; Facebook 1–2; X 1–2. ([Sprout Social via US Chamber](https://www.uschamber.com/co/grow/marketing/how-to-use-hashtags), [hashtagtools.io 2026 guide](https://hashtagtools.io/blog/youtube-hashtags-shorts-seo-guide-2026))
- **YouTube tags ≠ hashtags ≠ keywords.** Backend tags are a weak signal in 2026 ("tags past the eighth slot return effectively nothing"); hashtags in the description help categorization; keywords in title/description/script are the real SEO. ([KDCC: YouTube tags are dead in 2026](https://blog.kdcc.social/youtube-tags-are-dead-2026))
- **Consequence for us:** the winning design is *fewer, evidence-based tags* — derive the 3–5 hashtags from the topic's actual trending sources (what the trend engine saw), never stuff. This matches the project's honesty principles.

### 4.3 Cost levers

| Lever | Paying-api cost | Cheap path | Saving |
|---|---|---|---|
| **Narration TTS** | ElevenLabs ≈ $100/1M chars; OpenAI gpt-4o-mini-tts ≈ $16/1M | **Kokoro-82M** (Apache-2.0, ~$0 local CPU, $0.70/1M hosted; top-ranked open TTS on Artificial Analysis, ELO 1059) or Chatterbox (MIT, cloning) | ~60–140× |
| **Field extraction LLM** | gpt-4o-mini per section, per round (uncached) | Hash-keyed response cache + section batching + **Ollama** (serve with the model the repo already tracks) | 60–90% |
| **Script/metadata generation** | (currently template-only, $0 — keep the templates; add *optional* LLM polish behind cache) | — | Avoid scope creep into per-video LLM dependency |
| **YouTube publishing** | Dec 2025 quota change: uploads ≈ 100-unit bucket, 100 uploads/day | Publishing headroom is now plentiful; spend quota on *research*, not uploads | n/a |
| **Trend fetches** | Scraping =fragile + policy risk | Free official APIs (HF, HN, GitHub) + cached Trends wrapper | $0 |
| **Hosting** | Existing [cost-laptop-vps doc](cost-laptop-vps-2026-10-22.md) scenarios | Unchanged; caches ride existing Redis | n/a |

Sources: [Inworld TTS benchmarks](https://inworld.ai/resources/best-voice-ai-tts-apis-for-real-time-voice-agents-2026-benchmarks), [Picovoice on-device TTS](https://picovoice.ai/blog/on-device-tts), [BentoML open-source TTS](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models).

---

## 5. Target design

### 5.1 Trend Radar v2 — "a radar that watches by itself"

```
             ┌ new source adapters (7) ─────────────────────────────┐
             │ hf_papers · github_stars · hn_algolia · g trends     │
             │ yt_velocity · reddit_rss · newsletter_rss            │
             └──────────────┬───────────────────────────────────────┘
                            ▼  items (existing, deduped, trust-tiered)
   ┌────────────────────────────────────────────────────────────────┐
   │ trend_engine v2                                                │
   │  · story clustering (URL+title shingles, provider normal)      │
   │  · per-topic time series (trend_observations, 1 row/scan)      │
   │  · VELOCITY score: Δ(sources, points, stars, upvotes)/hour     │
   │  · corroboration: N independent sources ≥ Tier-B               │
   │  · existing 6 scores preserved + momentum + corroboration      │
   └──────────────┬─────────────────────────────────────────────────┘
                  ▼ trend_topics (cluster) → trend_candidates (existing)
   human shortlist OR (autopilot guardrails) ──► PRODUCTION QUEUE (5.2)
```

New/changed pieces:

1. **Adapters** (`packages/source_adapters/`): `hf_papers.py`, `hn_algolia.py`,
   `github_stars.py`, `google_trends.py` (trendspyg-style, fail-open), `reddit_rss.py`,
   plus config in the seeded registry. Each adapter records **evidence**: source URL,
   retrieval timestamp, raw payload hash — same discipline as offer snapshots
   (trend signals are *leads*, never verification evidence).
2. **Cadence + cache:** every fetch goes through Redis (existing instance) with a
   TTL per source (HF papers daily, HN 30 min, Trends 6 h) — free APIs stay free.
3. **Scheduled scan:** durable `trend_scan` job kind (like `collect:`), armed on
   creation and re-armed by the scan worker; `POST /trends/scan?reason=manual`
   still exists for the button. Scan becomes **incremental re-scoring** (no more
   one-shot `processed=TRUE`); each topic gets a row in
   `trend_observations(topic_key, ts, score_raw, score_parts JSON)` so velocity is
   real math, not age decay.
4. **Story clustering:** normalize provider/product entity + title shingles across
   items so 6 sources covering one story become one topic with corroboration count.

### 5.2 Production Queue — the ranked "videos to make" list

One new table + one list. This is what the operator opens every morning.

- `production_queue` rows are created from **promoted trend topics** and from
  **verified offers awaiting capture**; each row carries: offer link (optional),
  trend snapshot (score, velocity, sources-with-evidence), evidence readiness
  (0–100), preset fit (which video format this topic supports), freshness
  deadline (offer expiry), and `score = weighted(trend, evidence, freshness, fit)`.
- **Endpoints:** `GET /production-queue` (keyset), `POST /trends/{id}/promote`
  (creates offer-from-trend AND queue row in one transaction — closes gap #2),
  `POST /queue/{id}/archive`, `POST /queue/reorder` (operator override pins).
- **Dashboard:** `/queue` page rebuilt to show the ranked list with badges
  (🔥 velocity ↑, ⏳ expires in 3 d, 🧪 evidence ready) and one primary action per
  state: Promote → Verify → Prepare capture → Record.
- Editor mix guardrail (mirrors the 60/30/10 pillar policy in
  [enhancement plan §7B](enhancement-plan-2026-10-22.md)): queue marks rows
  evergreen vs timely and autopilot caps timely rows per day.
- **Auto-expiry:** queue rows expire when their offer expires or when trend
  velocity decays below floor for 7 days → archived with reason (closes the
  stale-lead leak where recommendations say "refresh N stale leads" forever).

### 5.3 One-click schedule & publish

Keep every existing gate; remove the click-count.

1. **`POST /offers/{id}/schedules/batch`** — one call creates the per-platform
   draft posts for exactly the platforms with a connected, tested account,
   attaching the same pinned render/package; platform-specific metadata each
   (current per-platform build paths stay, they're just invoked server-side).
2. **`POST /schedules/batch-transition`** — human-only (like other `require=True`
   writes) approve/reschedule/cancel on a validated id list; partial success
   returns per-id results; the dashboard calendar grows multi-select and an
   "Approve N ready →" button. Nothing here bypasses the release gate — the
   publish worker still runs its own gate per post.
3. **"Review → Schedule" wizard** on the offer page: package preview (all 4
   captions/metadata) → best-time suggestion (from `publish_windows` +
   measured metrics when available) → one click does create + mark for approval.
4. **On-demand pipeline kick:** with autopilot *off*, a new
   `POST /automation/run-now?stages=collect,scan,script,render` enqueues the
   owed work immediately (never touches human-gated stages) — the honest version
   of "one button" given capture must stay human.

### 5.4 Hashtag & packaging engine (evidence-based, platform-correct)

Rewrite `seo.py` hashtag logic as `hashtags.py` with a **per-platform capability
table** and a **trending-source bridge**:

| Platform | Tags | Where | Source of truth |
|---|---|---|---|
| YouTube | 3–5 hashtags **into the description tail** (first 3 show above title) + keep 5–8 plain backend tags | description + `tags` field | topic keywords + trend-engine terms; no stuffing |
| TikTok | 3–5 in caption | caption | trend terms only if the topic has actual TikTok/trend signal; `#Shorts`-analog avoided; never invented/viral tags |
| Instagram | 3–5 | caption tail | same |
| Facebook | 0–2 | caption tail (currently inconsistent — fix) | provider/topic tag only |

- **Generation:** deterministic-first (provider CamelCase + topic keyword + existing
  trend-engine keywords — all already present in evidence), **optional** LLM polish
  via the shared, cached LLM client with the wording guard applied. No invented
  tags: a hashtag must trace to evidence text or the trend row that produced it.
- **Feedback loop:** `workers/metrics` already snapshots per-post outcomes — add
  `hashtag_performance` rollup (tags → impressions/CTR per platform) consulted at
  generation time; tags that consistently underperform drop out of the pool.
- **Tests:** platform limits, dedup, casing, description placement, gate reasons
  for malformed tags (extend existing metadata gate reasons).

### 5.5 Cost engine — see the money, cap the money

1. **Usage ledger:** migration `0XX_llm_usage.sql` → `usage_events(kind, provider,
   model, units, unit_type, cost_usd_est, ref_type, ref_id, created_at, meta)`.
   Emit at: LLM extraction (tokens in/out), TTS (characters), trend fetches
   (requests), YouTube quota (units by endpoint from response headers when present).
2. **Budgets as guardrails:** automation guardrails gain
   `max_llm_cost_per_day_usd`, `max_tts_chars_per_day`; the worker checks the
   ledger *before* spending, fail-closed (a blocked stage shows in Needs-You).
3. **Caches (Redis-first, Postgres fallback):**
   - `extract:{content-hash}:{model}` → extraction JSON (re-verifications free)
   - `tts:{sha256(text+voice+model+speed)}` → narration path (re-renders free)
   - `trend:{source}:{key}` → raw fetches (TTL per source)
   - `hashtags:{platform}:{topic}` → trending-tag lookups (6 h TTL)
4. **Local-first providers:** a small provider layer in `extractors.py`/`narration.py`
   supporting OpenAI-compatible base URLs with a **capability probe** at worker
   start (`GET /api/tags` for Ollama, model presence, context length) — surfaced on
   the dashboard Settings card ("Extraction: ollama/qwen2.5:7b — reachable ✓").
   `Kokoro` TTS via the same OpenAI-compatible speech shim; `.env.example` gains a
   fully documented `VERIFY_LLM_*` / `TTS_*` / `COST_*` block.
5. **Cost visibility:** Settings → **Costs** card: today/7d/30d spend estimate,
   per-stage split, cache-hit rate; `/analytics` adds cost-per-published-video.

### 5.6 Robustness close-outs

1. **Token lifecycle:** Instagram/FB long-lived-token exchange job on a 45-day
   cadence + TikTok refresh where the app supports it; monitor keeps alerting as
   the fallback. Failure → attention item, never a silent stall.
2. **Rate-limit handling:** `platforms/base.py` error taxonomy gains
   `RateLimited(retry_after)`; adapters parse `Retry-After`/`x-ratelimit-*`; the
   publish retry path respects server-provided delay before its own backoff.
3. **LLM client hardening:** timeout + 2 retries with jitter + request budget per
   run; failures record `extraction.method=rules_fallback` honestly instead of
   silent None.
4. **Media retention job:** `media_gc` job honors the 90-day doc policy for
   *non-pinned* artifacts only (anything referenced by an approved schedule is
   pinned and exempt; dry-run flag first).
5. **Bulk un-wedge:** `POST /jobs/bulk-retry` (human-only, filter-checked) for the
   "50 jobs dead-lettered in an outage" morning.
6. **Deferred P2 carry-over** from [system-review-2026-10-23.md](system-review-2026-10-23.md)
   folded in where adjacent: render-lease renewal for >1 h encodes; trends
   summary/bands `page_total` rename; analytics cache payload normalization.

---

## 6. Work packages

Estimates assume one developer; each WP lands with tests in the same PR.

### WP-A — Trend ingestion adapters + registry (≈2 d)
- [ ] `packages/source_adapters/hf_papers.py` — daily papers, `sort=trending`, evidence fields
- [ ] `packages/source_adapters/hn_algolia.py` — points/comments velocity per keyword
- [ ] `packages/source_adapters/github_stars.py` — Δstars/day on watched repos
- [ ] `packages/source_adapters/google_trends.py` — trending-now + interest wrapper, fail-open, Tier-B
- [ ] `packages/source_adapters/reddit_rss.py` — lead-signal only
- [ ] Redis-backed fetch cache + per-source TTL; robots/egress policy respected
- [ ] `seed_sources.py` + `docs/source-registry.md` updated (trust tiers: HF official = A-lead, HN/GTrends = B)
- [ ] Tests: adapter units (fixture payloads), egress/permission tests extended
- **Accept:** ≥20 new lead items/day flow in from ≥3 new sources with evidence hashes, deduped by story.

### WP-B — Trend engine v2: clustering, history, velocity (≈3 d)
- [ ] Migration: `trend_topics` (cluster), `trend_observations` (time series)
- [ ] Story clustering (entity normalize + title shingles)
- [ ] Incremental re-scan (remove one-shot `processed=TRUE` semantics; keep API back-compat)
- [ ] Velocity + corroboration scores; bands recomputed; growth-engine recommendation wiring cleaned (no more perpetual "refresh N leads")
- [ ] Durable `trend_scan` job; re-armed after each scan; manual `/trends/scan` retained
- **Accept:** a topic pulsing on 3 sources over 6 h shows rising velocity; `trends` API UI shows sparkline + "why trending" (source list with evidence times).

### WP-C — Production queue + trend→offer bridge (≈2 d)
- [ ] Migration: `production_queue`
- [ ] `POST /trends/{id}/promote` (offer-from-trend, single transaction, audited, human or guardrail-gated)
- [ ] `GET /production-queue`, archive/reorder endpoints; auto-expiry job
- [ ] Dashboard `/queue` page (ranked, badges, per-state primary action)
- **Accept:** clicking Promote on a radar topic yields a verified-track offer and a queue row; queue rank matches documented formula; expired rows self-archive with reason.

### WP-D — One-click scheduling (≈2 d)
- [ ] `POST /offers/{id}/schedules/batch` (per-platform metadata, same pins)
- [ ] `POST /schedules/batch-transition` (human-only; per-id results)
- [ ] Calendar multi-select + "Approve N ready"; offer-page Review→Schedule wizard
- [ ] `POST /automation/run-now` (owed-work enqueue, never human stages)
- **Accept:** a fresh render can go from ready → scheduled on 3 platforms in ≤2 clicks without policy change; every created row passes the existing release-check story.

### WP-E — Hashtag & packaging engine (≈2 d)
- [ ] `services/api/hashtags.py` with platform capability table (YT desc tail, FB 0–2, IG/TikTok 3–5)
- [ ] Trend-bridged tag generation (deterministic first, optional cached LLM polish, wording-guarded, evidence-traceable)
- [ ] Fix FB/IG/TikTok caption inconsistencies; YouTube description hashtag line
- [ ] `hashtag_performance` rollup in metrics worker; generation consults it
- [ ] Release-gate reasons extended; tests for limits/dedup/placement
- **Accept:** per-platform packages each meet documented 2026 limits; every hashtag cites evidence or trend row; gate blocks violations.

### WP-F — Cost engine (≈3 d)
- [ ] Migration: `usage_events`; emitters in extractors/narration/trend fetch/yt quota
- [ ] Guardrails: `max_llm_cost_per_day_usd`, `max_tts_chars_per_day` (fail-closed, Needs-You)
- [ ] Caches: extract, TTS, trend, hashtags (Redis, Postgres fallback)
- [ ] Provider layer + capability probe (Ollama model list, Kokoro shim); Settings → Costs card; `.env.example` documented
- **Accept:** re-verification of an unchanged page costs 0 tokens; re-render costs 0 TTS chars; cost card shows per-stage 30-day spend; budgets trip correctly in tests.

### WP-G — Robustness close-outs (≈2 d)
- [ ] IG/FB token refresh job + TikTok refresh where supported
- [ ] `RateLimited` taxonomy + Retry-After parsing across adapters
- [ ] LLM client retries/jitter/budget + honest `rules_fallback` attribution
- [ ] `media_gc` dry-run job (pinned-artifact-aware)
- [ ] `POST /jobs/bulk-retry`
- [ ] Lease renewal for >1 h renders; trends `page_total`; cache normalization (carried P2s)
- **Accept:** token-expiry drill (set an expired token date +7d in a test) self-heals or alerts-then-heals; a mocked 429 with Retry-After delays exactly that schedule only.

### WP-H — Calendar & analytics polish (≈1–2 d, optional tail)
- [ ] Week grid + per-platform/day publish windows; conflict highlight (same window+platform)
- [ ] Best-time suggestions from measured metrics; cost-per-video in `/analytics`
- **Accept:** two same-window same-platform posts are visibly flagged before approve.

---

## 7. Sequenced to-do (dependency order)

1. **WP-A** adapters (feeds everything) →
2. **WP-B** engine v2 (needs items+history) →
3. **WP-C** queue+promote (needs engine) →
4. **WP-D** one-click scheduling (needs queue-ready entities) →
5. **WP-E** hashtags (needs trend terms; independent of D) →
6. **WP-F** cost engine (independent; do after E so hashtag fetches are covered) →
7. **WP-G** robustness (independent; interleave anytime) →
8. **WP-H** polish →
9. Operator docs: `go-live-checklist.md` (new env knobs), `source-registry.md`,
   `runbook.md` (trend-job + token-refresh playbooks), `master-plan-traceability.md`.

**Definition of done for the whole plan:** an operator opens `/queue`, sees
evidence-backed trending topics ranked, promotes one, and — with existing human
gates untouched — reaches scheduled posts on all connected platforms in as few
clicks as the policy allows, while Settings→Costs shows exactly what it cost.

---

## 8. Risks & guardrails

| Risk | Mitigation |
|---|---|
| Google Trends wrapper breaks (unofficial endpoints) | Fail-open adapter, Tier-B lead only, cached last-good, never blocks the scan |
| Scraping-prohibited surfaces (TikTok Creative Center) | Never scrape; manual typed evidence (existing 3-competitor flow) or optional paid API behind an explicit setting + legal review |
| YouTube quota burn from velocity probes | Hard keyword budget/day, single cached `search.list` per keyword per interval, units logged in `usage_events` |
| Hashtag stuffing → spam signals | 3–5 max per platform by construction; evidence-traceable tags only; metrics feedback retires losers |
| Autopilot + LLM = runaway spend | Budget guardrails fail-closed; default Assisted; usage ledger visible before autopilot is ever enabled |
| Velocity gaming / hot-but-false topics | Trend signals are leads only: verification (official evidence) still gates everything downstream — unchanged |
| Scope creep into "AI-written everything" | Scriptgen stays template-first; LLM is optional polish behind cache + wording guard, consistent with the inauthentic-content policy caution in the 10-22 plan |

---

## 9. Cost model (indicative, monthly, 30 videos)

| Item | Before | After |
|---|---|---|
| Narration TTS (≈25k chars/video, cloud) | ~$75–125 (ElevenLabs-class) | **~$0** local Kokoro / ≤$0.60 hosted-cheapest |
| Extraction LLM (re-verify rounds, uncached) | variable, unmeasured | −60–90% via cache+batch; $0 on Ollama |
| Trend data | manual hours | $0 (free APIs) or ~$0–49 optional |
| YouTube API | $0 (quota-finite) | $0; research budgeted ~2k units/day |
| **New visibility** | none | `usage_events` + Settings→Costs + per-video cost in analytics |

Human time remains the dominant cost (capture stays human by design); the queue
and batch actions cut clicks, and capture batch-prep (listed under gap #15) can
join WP-C scope if needed.

---

## 10. Related documents

- [enhancement-plan-2026-10-22.md](enhancement-plan-2026-10-22.md) — baseline audit & two-month hardening (superseded sections noted in its resolution banner)
- [system-review-2026-10-23.md](system-review-2026-10-23.md) — fixed/deferred dispositions this plan carries forward
- [cost-laptop-vps-2026-10-22.md](cost-laptop-vps-2026-10-22.md) — hosting scenarios this plan's caches ride on
- [automation-and-human-control.md](automation-and-human-control.md) — policy/guardrail system new budgets join
- [source-registry.md](source-registry.md) — where new adapters register
- [render-qc.md](render-qc.md) / [go-live-checklist.md](go-live-checklist.md) — unchanged release gates
