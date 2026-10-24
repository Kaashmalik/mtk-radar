# Source Registry

Every source is registered here before any collector may poll it (master plan §2 and §14). Assign: owner, official domain/account, collection method, reliability class (trust tier), polling cadence, and last-checked time.

**Tier rules** — A: provider-owned, can support verification · B: discovery leads only, create candidates · C: excluded until official confirmation exists.

## Tier A — provider-owned (verification-grade)

| Source | Category | Collection | Cadence | Notes |
|---|---|---|---|---|
| Hugging Face — Inference Providers pricing/docs | Model hubs | Page watch + docs feed | Daily | Pricing is the authority for "free" claims: huggingface.co/docs/inference-providers/pricing |
| Hugging Face Hub model catalogs | Model hubs | huggingface_hub API | 6h | Model availability ≠ free inference; verify provider pricing separately |
| OpenAI / Anthropic / Google AI changelogs & pricing pages | Dev platforms | Page watch / official feeds | 6h | Recheck model availability, quotas, regions |
| GitHub release feeds (maintainer repos: OpenCode, Ollama, llama.cpp, vLLM) | Coding tools | GitHub REST releases | 4h | docs.github.com/en/rest/releases |
| GitHub Education / Student Developer Pack | Student programs | Page watch | Daily | Country, enrollment proof, deadline |
| MLH official site/programs | Student programs | Page watch | Daily | mlh.io — separate education benefits vs event prizes |
| Cloud startup programs (AWS Activate, Google for Startups, MS for Startups, Oracle, NVIDIA) | Cloud startup | Page watch | Weekly | Application-based ≠ universal credits — verify eligibility carefully |
| Registrar partner terms (.TECH et al.) | Domains | Page watch | Daily | Record promo code, redemption URL, renewal price, auto-renew, expiry |

## Tier B — discovery leads (candidate creation only)

Seeded trend-signal collector sources (Trend Radar v2, WP-A —
[enhancement plan 2026-10-24](enhancement-plan-2026-10-24-trends-automation.md)).
Every signal feeds the radar's scoring; none can verify an offer:

| Source | Category | Collection | Cadence | Notes |
|---|---|---|---|---|
| Hugging Face Papers | Research papers | Official `daily_papers` API (`sort=trending`-style feed) | Daily | Upvote count is the community signal; the HF paper page is the discovery trail, not evidence |
| Hacker News | Trend signals | Free Algolia search API (`hn.algolia.com/api/v1`), points/age filters | 6h | Point/comment velocity per keyword — no scraping, no key |
| Reddit r/LocalLLaMA | Trend signals | Public `new.json` endpoint, descriptive UA, one small page | 6h | Score/comment counts; polite-usage only, leads never evidence |
| GitHub Stars | Trend signals | Official REST repo metadata | Daily | Change-only snapshots (star count in the external id) form a velocity series at the radar |
| Google Trends (US, PK) | Trend signals | Public `trending/rss` feed | 6h | Unofficial endpoint — fail-open wrapper; trending placement proposes topics only |

Other Tier-B signals (manual / evaluated, not collector-polled):

| Source | Collection | Notes |
|---|---|---|
| X posts | Manual / API where permitted | Never sufficient for verification |
| Community Discord/Telegram announcements | Manual / bot where permitted | Official-sounding ≠ official |
| TikTok Creative Center trend modules | Manual typed entry only | Scraping prohibited (2026 transparency rules); use the 3-competitor evidence form |
| Curated free-LLM lists (cheahjs, mnfst, for-the-zero) | Diff repo updates | Lead generators only — verify on provider page |

## Tier C — excluded pending proof

Coupon aggregators, unknown link shorteners, influencer claims without evidence, leaked codes. No claim guide or video until official confirmation is found.

## Adding a source checklist

- [ ] Domain/account verified as provider-owned
- [ ] Collection method respects robots/terms + rate limits
- [ ] Trust tier assigned; cadence set; owner recorded
- [ ] Seed row added to `sources` table; adapter implemented or `manual`
