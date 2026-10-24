"""Seed the source registry with the initial Tier-A list (docs/source-registry.md).

Run:  python -m scripts.seed_sources   (from services/api/, with DATABASE_URL set)
      or: docker compose exec api python -m scripts.seed_sources
"""

import asyncio
import json
import os

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://mtk:mtk@localhost:5432/mtk_radar")

SOURCES = [
    # --- Model hubs & inference ---
    {
        "provider": "Hugging Face",
        "canonical_domain": "huggingface.co",
        "category": "model_hubs",
        "adapter": "page_watch",
        "config": {"url": "https://huggingface.co/docs/inference-providers/pricing"},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "24 hours",
    },
    {
        "provider": "Hugging Face Hub",
        "canonical_domain": "huggingface.co",
        "category": "model_hubs",
        "adapter": "manual",  # huggingface_hub library collector (later phase)
        "config": {},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "6 hours",
    },
    # --- AI developer platforms (official changelogs/pricing) ---
    {
        "provider": "OpenAI",
        "canonical_domain": "openai.com",
        "category": "dev_platforms",
        "adapter": "page_watch",
        "config": {"url": "https://help.openai.com/en/articles/8550641-api-release-notes"},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "6 hours",
    },
    # --- Open-source coding tools (maintainer release feeds) ---
    {
        "provider": "Ollama",
        "canonical_domain": "github.com",
        "category": "coding_tools",
        "adapter": "github_releases",
        "config": {"repo": "ollama/ollama"},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "4 hours",
    },
    {
        "provider": "llama.cpp",
        "canonical_domain": "github.com",
        "category": "coding_tools",
        "adapter": "github_releases",
        "config": {"repo": "ggml-org/llama.cpp"},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "4 hours",
    },
    {
        "provider": "vLLM",
        "canonical_domain": "github.com",
        "category": "coding_tools",
        "adapter": "github_releases",
        "config": {"repo": "vllm-project/vllm"},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "4 hours",
    },
    # --- Student & community programs ---
    {
        "provider": "GitHub Education",
        "canonical_domain": "education.github.com",
        "category": "student_programs",
        "adapter": "page_watch",
        "config": {"url": "https://education.github.com/pack"},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "24 hours",
    },
    {
        "provider": "MLH",
        "canonical_domain": "mlh.io",
        "category": "student_programs",
        "adapter": "page_watch",
        "config": {"url": "https://mlh.io/seasons/2026/events"},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "24 hours",
    },
    # --- Cloud & startup programs ---
    {
        "provider": "AWS Activate",
        "canonical_domain": "aws.amazon.com",
        "category": "cloud_startup",
        "adapter": "page_watch",
        "config": {"url": "https://aws.amazon.com/activate/"},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "7 days",
    },
    # --- Domains & software perks ---
    {
        "provider": ".TECH Domains",
        "canonical_domain": "get.tech",
        "category": "domains_software",
        "adapter": "page_watch",
        "config": {"url": "https://get.tech/"},
        "trust_tier": "A_provider_owned",
        "polling_cadence": "24 hours",
    },
    # --- Trend signals (Tier-B: momentum leads — NEVER verification evidence).
    # Registered for the Trend Radar v2 (docs/enhancement-plan-2026-10-24-
    # trends-automation.md, WP-A). Each feed is official/free; upvotes, points,
    # star counts and trending placement only propose topics for the radar.
    {
        "provider": "Hugging Face Papers",
        "canonical_domain": "huggingface.co",
        "category": "research_papers",
        "adapter": "hf_papers",
        "config": {},
        "trust_tier": "B_discovery_lead",
        "polling_cadence": "24 hours",
    },
    {
        "provider": "Hacker News",
        "canonical_domain": "news.ycombinator.com",
        "category": "trend_signals",
        "adapter": "hn_search",
        "config": {"query": "AI", "min_points": 100, "max_age_hours": 48, "limit": 15},
        "trust_tier": "B_discovery_lead",
        "polling_cadence": "6 hours",
    },
    {
        "provider": "Reddit r/LocalLLaMA",
        "canonical_domain": "reddit.com",
        "category": "trend_signals",
        "adapter": "reddit_new",
        "config": {"subreddit": "LocalLLaMA", "min_score": 100,
                   "max_age_hours": 48, "limit": 20},
        "trust_tier": "B_discovery_lead",
        "polling_cadence": "6 hours",
    },
    {
        "provider": "GitHub Stars",
        "canonical_domain": "github.com",
        "category": "trend_signals",
        "adapter": "github_stars",
        "config": {"repos": [
            "ollama/ollama", "ggml-org/llama.cpp", "vllm-project/vllm",
            "huggingface/transformers", "langchain-ai/langchain",
        ]},
        "trust_tier": "B_discovery_lead",
        "polling_cadence": "24 hours",
    },
    {
        "provider": "Google Trends US",
        "canonical_domain": "trends.google.com",
        "category": "trend_signals",
        "adapter": "google_trends_rss",
        "config": {"geo": "US"},
        "trust_tier": "B_discovery_lead",
        "polling_cadence": "6 hours",
    },
    {
        "provider": "Google Trends PK",
        "canonical_domain": "trends.google.com",
        "category": "trend_signals",
        "adapter": "google_trends_rss",
        "config": {"geo": "PK"},
        "trust_tier": "B_discovery_lead",
        "polling_cadence": "6 hours",
    },
]


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    created = skipped = 0
    for src in SOURCES:
        exists = await conn.fetchrow(
            "SELECT id FROM sources WHERE provider = $1 AND COALESCE(canonical_domain, '') = $2",
            src["provider"],
            src.get("canonical_domain", ""),
        )
        if exists:
            skipped += 1
            continue
        await conn.execute(
            """
            INSERT INTO sources (provider, canonical_domain, category, adapter,
                                 config, polling_cadence, trust_tier)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::text::interval, $7::trust_tier)
            """,
            src["provider"],
            src.get("canonical_domain"),
            src["category"],
            src["adapter"],
            json.dumps(src.get("config", {})),
            src.get("polling_cadence", "6 hours"),
            src["trust_tier"],
        )
        created += 1
        print(f"+ registered: {src['provider']} [{src['adapter']}]")
    await conn.close()
    print(f"\ndone: {created} registered, {skipped} already present")


if __name__ == "__main__":
    asyncio.run(main())
