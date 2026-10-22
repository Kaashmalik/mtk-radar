# MTK Codex — brand, niche & growth research (22 October 2026)

Research for the MTK Codex content channel strategy, checked against live
sources and the existing portfolio. Feeds the mtk-radar system (§7 growth
plan, `settings.brand`).

---

## 1. Brand audit — "MTK Codex"

### Verdict: keep the name. It is good.

- **Distinctive + brandable**: short, techy ("Codex" implies systems/keys/code),
  easy to say and spell, works as a personal-company hybrid.
- **No blocking conflicts found**: searches surface only unrelated noise (a
  Greek bearings distributor, academic citations, name-directory variants).
  The active "MTK CODEX" footprints ARE yours (Facebook IT-company page in
  Lahore, LinkedIn `muhammadkashif-mtkcodex`, `mtkcodex.site` subdomains).
  No obvious trademark clash in consumer tech/software space.
- **Handles found during research:**
  | Platform | Handle `@mtkcodex` | Status |
  |---|---|---|
  | YouTube | [youtube.com/@mtkcodex](https://www.youtube.com/@mtkcodex) | **Available (404 at research time — register immediately)** |
  | Facebook | facebook.com page "MTK CODEX" | **Yours already** |
  | LinkedIn | `muhammadkashif-mtkcodex` | Yours already |
  | Instagram | instagram.com/mtkcodex | Login-walled — verify manually, same day |
  | GitHub | current: `Kaashmalik` | Recommend creating `github.com/mtkcodex` org, keep personal account |

  **Action: register `@mtkcodex` on YouTube, Instagram, TikTok, X, and the
  GitHub org the same week** — handle squatting is the only real damage
  competitors can do to a brand name.

### Domain findings
- `mtkcodex.site` is live and in production use (`pf.`, `dairy.`,
  `instalease.` subdomains).
- Recommend buying **`mtkcodex.com`** (most people type .com, always route
  it → .site) and a branded email (`hello@mtkcodex.site`) — a gmail address
  on a "$5k+ SaaS" pricing page costs trust.

### Portfolio audit (pf.mtkcodex.site) — checked live
**Strong:** real numbers (7 platforms, 500+ tenants, 50K+ tracked entities),
case studies with live demos + GitHub repos, clear pricing tiers, CV, 12h
response promise, WhatsApp + form. This is better positioning evidence than
most competitors' portfolios.

**Fixes recommended (spotted in the live markup):**
1. **Zero-counters**: "0 Production SaaS", "0+ Tenants", "0+ API Endpoints",
   "0+ Lighthouse Score" render as literal zeros in raw HTML (JS animated
   counters). No-JS users and search crawlers see zeros — replace with
   server-rendered final numbers that animate *from* zero.
2. **Leaked dev path**: `/home/kashif/profile.jpg` appears as an image path in
   the About section — a server filesystem path leaked into production markup.
3. **Copy bug**: footer reads "Built with using Next.js 16" (double preposition).
4. Breakout case-study pages with real URLs (one per platform, targeting
   keywords like "multi-tenant SaaS case study cricket league software") —
   the current one-page anchors have no individual search presence.
5. Add structured data (`Person`/`Organization` schema) + OG tags for rich
   results and social cards.

---

## 2. Best-fit niche (evidence-based, 2026)

### The niche: **"Production SaaS, built in public — by a working SaaS architect"**

Not generic "tech tutorials". The research converges on these facts:

| Signal (2026 sources) | Data |
|---|---|
| SaaS & software tutorials CPM | **$18–$35** (fluxnote 2026 ranking, #2 overall) |
| B2B/SaaS review CPM | $10–$30, premium advertisers (vidIQ 2026) |
| Tech/SaaS sponsorship rates | **$30–$60 CPM** (launchpointhq 2026) |
| B2B creator growth rates | **28–35% quarterly — highest of all tracked niches** (influenceflow 2026 study) |
| "Indie SaaS build-in-public" | Listed as a top trending niche by vidIQ's 2026 guide |
| Algorithm's 2026 priority | Niche consistency — mixing content types cuts Shorts reach **40–52%** |

**Why this beats the alternatives for YOU specifically:**
- Generic AI-news/faceless channels: low moat, races trends, your CPM there
  competes with millions.
- Personal-finance has higher CPM but zero relation to your credibility.
- **Your unfair advantage**: you have 7 shipped multi-tenant platforms with
  real tenants. 95% of dev-tutorial channels teach toy apps. Nobody else in
  the Pakistan/UK/AUS market teaches *Postgres RLS multi-tenancy, Clerk
  Organizations, offline-first React Native, and local payment rails
  (JazzCash/EasyPaisa)* from live production systems. That is content
  competitors cannot copy without your receipts.

### Three content pillars (aligned with mtk-radar §7)

1. **Production tutorials (search-first, evergreen)** — the compounding asset.
   Small channels outrank big ones in YouTube *search* when the video better
   satisfies the query (vidIQ 2026) — search is the small-channel lane.
2. **Build-in-public: MTK Codex case studies** — "How I built a dairy SaaS
   running 500+ farms", breakdown of InstalEase, SSL league platform. Trust +
   personality + client funnel. Case-study content converts clients.
3. **AI integration in production** (OpenAI/Vercel AI SDK/TensorFlow.js) —
   highest-velocity 2026 search demand, and it is literally in your shipped
   stack (SSL's 5-language AI commentary, AlertPro's on-device detection).

### Pakistan-specific wedge (low competition, high relevance)
"JazzCash/EasyPaisa integration tutorial", "SaaS payments in Pakistan",
"freelance to product agency PK" — near-zero competition, permanent demand,
attracts the local builder audience that hires/recommends you.

---

## 3. Keyword bank (from 2026 gap/competition research)

**Tier 1 — searchable, buyable intent (long-form titles):**
- `build multi-tenant SaaS Next.js [year]`
- `Supabase RLS multi-tenant tutorial`
- `Clerk Organizations tutorial [year]`
- `Stripe + JazzCash subscription tutorial`
- `NestJS microservices real project`
- `React Native offline sync (WatermelonDB)`
- `Electron app from scratch [year]`
- `ship a SaaS in 30 days` (series title — series formats are explicitly
  rewarded by the 2026 algorithm)
- `SaaS architecture case study [real product]`
- `OpenAI streaming chatbot Next.js production`

**Tier 2 — Shorts hooks (22–45s, first-second payoff):**
- "This SaaS mistake cost my client 3 months" / "500 farms, one database —
  here's the trick" / "RLS in 30 seconds" / "Steal my SaaS stack" /
  "$0 → production on Vercel" (pattern hook)
- Cut every Short from a long-form video (repurposing is the 2026 meta —
  dual-format creators reach 100K ~13–14 months vs 16–18 Shorts-only).

**Tier 3 — avoid as primary keywords:** `next js tutorial` (saturated by
full-course videos from large channels), `learn programming` (no intent).
Attack the long-tail where the gap reports show missing coverage.

**Recommended brand metadata (drop into mtk-radar `settings.brand`):**
```json
{
  "website_url": "https://pf.mtkcodex.site",
  "cta": "Build your SaaS with me → pf.mtkcodex.site",
  "languages": ["en"],
  "hashtag_sets": {
    "tutorials": ["nextjs", "supabase", "saas", "webdevelopment", "programming"],
    "buildinpublic": ["buildinpublic", "indiehacker", "saas", "startup", "coding"],
    "ai": ["openai", "ai", "nextjs", "saas", "aitutorial"]
  }
}
```

---

## 4. Growth mechanics (what the 2026 data actually says)

| Mechanism | 2026 finding | So, for MTK Codex |
|---|---|---|
| Shorts & long-form | Two **separate** ranking models since late 2025 | Both, deliberately: Shorts = discovery feed, long-form = business |
| Shorts length sweet spot | **22–45s**, retention ≥65% (<30s) / ≥50% (30–60s) | Cut ruthlessly; payoff in second 1 |
| Posting frequency | 2–4 Shorts/week = per-post peak (5,872 avg views, Metricool 2026 study) | 3 Shorts + 1 long-form/week, fixed days |
| Hook | Viewed-vs-swiped decided in 1–3s | Test hook variations, don't polish one |
| Niche consistency | Cross-topic mixing cuts Shorts reach 40–52% | Only the 3 pillars, nothing else |
| Search (small channels) | Long-tail queries: better answer wins, size irrelevant | Target Tier-1 keywords; evergreen how-to library first |
| Satisfaction signals | Post-watch surveys feed ranking; dislikes/skip matter | Plan is truth-first — keep claims verifiable |
| Cross-surface amplification | Top Shorts get planted on home feed beside long-form | End every Short pointing at its long-form |
| Conversion reality | Shorts subscribe at <10% the rate of long-form; sponsorships priced off engaged long-form | Long-form is the business; Shorts are the ads for it |

**Funnel:** Short → long-form → description link (pf.mtkcodex.site + GitHub)
→ client inquiry. The Scalelist case study (2026): a tiny channel brought
**50% of a SaaS's paid users**. Chatwith: 500K monthly views → 5K
signups/month. This is the business model: YouTube as client-acquisition
moat, sponsorships ($30–60 CPM B2B) as the second stream, AdSense last.

**First 10 videos (order matters — evergreen library before trends):**
1. How I Built a Dairy SaaS Running 500+ Farms (case study)
2. Multi-Tenant SaaS with Supabase RLS — from zero to production
3. I Built 7 SaaS Platforms — here's the exact stack
4. Next.js 16 + NestJS + Supabase: the production setup I use for clients
5. Stripe subscriptions in Next.js — the complete 2026 build
6. JazzCash/EasyPaisa integration for SaaS (Pakistan)

7. On-device AI: turning any IP camera into a smart cam (MTK AlertPro build)
8. AI commentary in 5 languages — the cricket-league SaaS architecture
9. React Native offline sync that actually works
10. From freelancer to SaaS studio: my full client-to-production workflow

**Cadence math:** 1 long-form + 3 Shorts/week ≈ 8.7 hrs/week — your portfolio
already advertises 9+ hrs/day availability; this fits and compounds.

---

## 5. Sources (checked 22 Oct 2026)

- Live: pf.mtkcodex.site, dairy/instalease.mtkcodex.site references,
  youtube.com/@mtkcodex (404), instagram.com/mtkcodex, Facebook/LinkedIn presence
- vidIQ — "80 Best YouTube Niches for 2026", "How the YouTube Algorithm Works in 2026"
- Metricool — 2026 YouTube Study (Shorts frequency/retention data)
- usefastlane.ai — "The YouTube Shorts Algorithm in 2026"
- influenceflow.io — Shorts+long-form 2026 creator guide (B2B growth rates)
- fluxnote.io — high-CPM niches 2026 (SaaS $18–35)
- outlierkit.com, virlo.ai — RPM/CPM by niche 2026
- launchpointhq.com — tech/SaaS sponsorship rates 2026
- sellontube.com, pulsehero.substack.com — SaaS-founder YouTube case studies
- gillianperkins.com — 2026 algorithm shifts ( Shorts conversion caveat )
- creatorgap.in — "next js tutorial" content-gap report

*CPM/growth figures are third-party 2026 estimates, directional — not a
guarantee of revenue or views.*
