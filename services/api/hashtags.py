"""Hashtag & packaging engine (v0.36 — enhancement plan 2026-10-24, WP-E).

Evidence-based, platform-correct hashtags. Reads alongside the 2026 platform
rules:

| Platform | Tags | Where                  | Source of truth                     |
|----------|------|------------------------|-------------------------------------|
| YouTube  | 3–5  | description tail        | topic keywords + trend-engine terms |
|          |      |                        | (first 3 render above the title)    |
| TikTok   | 3–5  | caption                | topic/trend terms only; no #Shorts  |
| Instagram| 3–5  | caption tail           | same                                |
| Facebook | 0–2  | caption tail           | provider/topic tag only             |

Two hard rules:

1. **No invented tags.** Every hashtag traces to the verified offer fields
   (provider, category, region) or to the trend row that produced the topic —
   the same trust model as every other generator: we package evidence, we do
   not author it.
2. **Deterministic first.** The pool is ordered deterministically (feedback
   rollup, then source priority, then the tag itself), so the same inputs
   always produce the same package — reviewers approve a hash, not a roll of
   the dice. LLM polish (if ever wired in) must run the wording guard and
   cache its result; this module stays the floor.

The `hashtag_performance` rollup (migration 034, maintained at metrics
ingest) stores per-tag measured impressions. Its APPLICATION here —
re-ranking measured-best tags and sinking underperformers — is
permission-gated behind `MTK_ENABLE_DERIVED_ENGAGEMENT` (G21,
evidence-to-video plan): reordering generation from derived aggregates is
the same restricted metric class as the growth-score blend. Default
generation order is the deterministic source priority below; the rollup
remains available as plain stored data.
"""

from __future__ import annotations

import re
from typing import Any, Final

#: Per-platform capability table — the single source of truth for counts and
#: placement. `hashtag_min`/`hashtag_max` are this channel's EDITORIAL
#: preferences (small, relevant sets), not platform law; the release gate
#: enforces them and labels them as such. Hard provider rules live in
#: PLATFORM_RULES below and are cited separately.
CAPABILITIES: Final[dict[str, dict[str, Any]]] = {
    "youtube": {
        "hashtag_min": 3,
        "hashtag_max": 5,
        "placement": "description_tail",   # first 3 show above the title
        "backend_tags": (5, 8),            # plain keywords, no '#'
    },
    "instagram": {
        "hashtag_min": 3,
        "hashtag_max": 5,
        "placement": "caption_tail",
    },
    "tiktok": {
        "hashtag_min": 3,
        "hashtag_max": 5,
        "placement": "caption",
    },
    "facebook": {
        "hashtag_min": 0,
        "hashtag_max": 2,
        "placement": "caption_tail",
    },
}

#: Documented provider rules (distinct from editorial preferences). YouTube
#: Help: "If you add more than 60 hashtags, YouTube will ignore all hashtags
#: on that video" — re-verify at implementation time.
YOUTUBE_IGNORE_ALL_ABOVE: Final[int] = 60

#: Category → one niche tag. Deterministic mapping, no LLM in the loop.
_CATEGORY_TAG: Final[dict[str, str]] = {
    "student_programs": "student",
    "developer_tools": "developer",
    "model_hubs": "ai",
    "cloud_platforms": "cloud",
    "domains_hosting": "domain",
    "domains": "domain",
    "ai_tools": "ai",
    "education": "student",
    "startup_perks": "startup",
}

# Urdu hashtags (deterministic, category-mapped same as English above).
_URDU_CATEGORY_TAG: Final[dict[str, str]] = {
    "student_programs": "طالب_علم",
    "model_hubs": "مصنوعی_ذہانت",
    "domains_hosting": "ڈومین",
}
_URDU_DEFAULT_TAG = "ٹیکنالوجی"

#: Hashtag charset: Latin letters/digits/underscore, or Arabic-script letters
#: (Urdu), 1–60 characters after the '#'. Anything else is a gate violation,
#: not silently dropped.
HASHTAG_RE: Final = re.compile(r"^#[A-Za-z0-9_\u0600-\u06FF]{1,60}$")

#: Trend-bridged tags are proposals from a Tier-B lead — they inform demand,
#: they never state a fact. Banned vanity tags never leave the engine: they
#: are not evidence of anything.
FORBIDDEN_TAGS: Final[frozenset[str]] = frozenset({
    "#shorts", "#fyp", "#foryou", "#viral", "#trending", "#explore",
})


def capability(platform: str) -> dict[str, Any]:
    """The platform's capability row. Unknown platform → strict default."""
    return CAPABILITIES.get(platform) or CAPABILITIES["facebook"]


def hashtagify(value: str) -> str:
    """CamelCase a provider/phrase into one safe hashtag ('#' included)."""
    words = re.findall(r"[A-Za-z0-9]+", value or "")
    if not words:
        return ""
    # Split camel-humped single tokens ("AcmeDomains" → "AcmeDomains" stays —
    # the source is already a brand) and cap length at 40.
    tag = "".join(word[:1].upper() + word[1:] for word in words[:4])
    return f"#{tag[:40]}" if len(tag) > 1 else ""


def _normalize_candidate(value: str) -> str:
    """One tag from free text (a trend keyword, a category) — CamelCase."""
    return hashtagify(value)


def generate_hashtags(
    platform: str,
    *,
    provider: str = "",
    category: str = "",
    title: str = "",
    countries: list[str] | None = None,
    trend_keywords: list[str] | None = None,
    language: str = "en",
    performance: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Evidence-traceable hashtags for one platform, within its limits.

    Returns a list of ``{"tag", "source", "ref"}`` — every tag cites where it
    came from. `performance` maps tag → {"avg_impressions", "posts"} from the
    `hashtag_performance` rollup; when the derived-engagement permission is
    enabled (G21), tags with a meaningfully worse track record than the best
    measured tag sink below their still-unmeasured peers. With the permission
    off (default) this argument is ignored.

    Ordering (deterministic): measured-best → trend-bridged → niche →
    provider → regional. Duplicates collapse case-insensitively.
    """
    caps = capability(platform)
    low, high = caps["hashtag_min"], caps["hashtag_max"]

    pool: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(tag: str, source: str, ref: str) -> None:
        tag = tag.strip()
        if not tag or not HASHTAG_RE.match(tag):
            return
        if tag.lstrip("#").lower() in seen:
            return
        if tag.lower() in FORBIDDEN_TAGS:
            return
        seen.add(tag.lstrip("#").lower())
        pool.append({"tag": tag, "source": source, "ref": ref})

    # 1. Trend-bridged tags: only from the trend row that produced the topic.
    # Tier-B signals shape demand; they are cited, never presented as facts.
    for kw in (trend_keywords or [])[:6]:
        tag = _normalize_candidate(str(kw))
        if tag:
            add(tag, "trend", f"trend keyword '{kw}'")

    # 2. Niche tag from the offer category (an evidence field).
    cat = str(category or "").lower()
    if language == "ur":
        niche = _URDU_CATEGORY_TAG.get(cat) or _URDU_DEFAULT_TAG
        add(f"#{niche}", "category", f"offer category '{category or 'default'}'")
    else:
        niche = _CATEGORY_TAG.get(cat)
        if niche:
            add(f"#{niche[0].upper() + niche[1:]}", "category",
                f"offer category '{category}'")

    # 3. Provider tag — the brand, from the verified offer field.
    provider_tag = hashtagify(str(provider or ""))
    if provider_tag:
        add(provider_tag, "provider", f"offer provider '{provider}'")

    # 4. Regional tag from eligibility (verified field).
    for country in (countries or [])[:1]:
        regional = hashtagify(str(country))
        if regional:
            add(regional, "eligibility", f"eligibility country '{country}'")

    # Facebook officially tolerates 0–2; scale everything down to the cap.
    max_tags = high if low > 0 else min(2, high)

    # 5. Feedback rollup — PERMISSION-GATED (G21, evidence-to-video plan).
    # Re-ranking/sinking tags from measured platform aggregates is the same
    # class of independently-calculated metric as the growth-score blend, so
    # it only applies when the deployment opts in via
    # MTK_ENABLE_DERIVED_ENGAGEMENT. Default: source-priority order decides
    # (documented editorial heuristic); the rollup stays available as stored
    # native data, it just never reshapes generation. When gated OFF,
    # `performance` is ignored here.
    from growth_engine import derived_engagement_enabled

    perf = (performance or {}) if derived_engagement_enabled() else {}
    measured = [
        (tag.lower(), float((stats or {}).get("avg_impressions") or 0.0))
        for tag, stats in perf.items()
        if int((stats or {}).get("posts") or 0) >= 3
    ]
    best = max((avg for _, avg in measured), default=0.0)
    floor = best * 0.3 if best > 0 else 0.0

    def rank(item: dict[str, str]) -> tuple:
        stats = perf.get(item["tag"].lower()) or perf.get(item["tag"]) or {}
        posts = int(stats.get("posts") or 0)
        avg = float(stats.get("avg_impressions") or 0.0)
        if posts >= 3:
            if best and avg < floor:
                return (2, 0, item["tag"].lower())   # measured underperformer
            return (0, -avg, item["tag"].lower())    # measured, healthy
        # Unmeasured: keep the pool's source-priority order. Python's sort is
        # stable, so returning an equal key preserves the insertion order
        # (trend → category → provider → eligibility) and the cap can never
        # drop a higher-priority tag in favour of an alphabetical accident.
        return (1, 0, 0)

    pool.sort(key=rank)

    out: list[dict[str, Any]] = []
    for item in pool:
        if len(out) >= max_tags:
            break
        out.append(item)
    return out


def parse_hashtags(text: str) -> list[str]:
    """Extract the valid hashtags actually present in a caption/description."""
    seen: set[str] = set()
    out: list[str] = []
    for candidate in re.findall(r"#[A-Za-z0-9_\u0600-\u06FF]{1,60}", text or ""):
        key = candidate.lower()
        if key not in seen:
            seen.add(key)
            out.append(candidate)
    return out


def hashtag_gate_problems(platform: str, metadata: dict[str, Any]) -> list[dict[str, str]]:
    """Release-gate reasons for hashtag violations (WP-E).

    Extends the metadata gate: per-platform counts/placement from the SAME
    capability table the generator uses, plus charset and banned vanity tags.
    """
    problems: list[dict[str, str]] = []
    caps = capability(platform)
    caption = str(metadata.get("caption") or "")
    in_caption = parse_hashtags(caption)
    proposed = metadata.get("hashtags")
    proposed = proposed if isinstance(proposed, list) else []

    problems.extend(
        {"code": "hashtag_invalid", "detail": f"'{tag}' is not a valid hashtag "
         "(letters, digits, underscore; Arabic script allowed)", "blocking": True}
        for tag in (*proposed, *in_caption) if not HASHTAG_RE.match(str(tag))
    )
    problems.extend(
        {"code": "hashtag_forbidden", "detail": f"'{tag}' is a vanity tag — "
         "hashtags must cite evidence or the trend row that produced the "
         "topic", "blocking": True}
        for tag in (*proposed, *in_caption)
        if str(tag).lower() in FORBIDDEN_TAGS
    )

    if platform == "youtube":
        # Hashtags belong in the DESCRIPTION tail (first 3 render above the
        # title); the `tags` field stays plain keywords (checked separately).
        below, above = caps["hashtag_min"], caps["hashtag_max"]
        if len(in_caption) > above:
            problems.append({
                "code": "hashtag_count",
                "detail": (f"Channel preference is at most {above} description "
                           f"hashtags (found {len(in_caption)}) — an editorial "
                           "limit, not a YouTube rule; the first 3 render "
                           "above the title"),
                "blocking": True,
            })
        if len(in_caption) < below:
            # Advisory only: the generator proposes exactly the tags it can
            # trace to evidence — it must never invent filler to hit a quota.
            problems.append({
                "code": "hashtag_count",
                "detail": (f"Channel preference is {below}–{above} description "
                           f"hashtags (found {len(in_caption)}) — the engine only "
                           "ships evidence-traceable tags"),
                "blocking": False,
            })
        total = len({*map(str.lower, map(str, proposed)), *map(str.lower, in_caption)})
        if total > YOUTUBE_IGNORE_ALL_ABOVE:
            problems.append({
                "code": "hashtag_count",
                "detail": (f"YouTube ignores ALL hashtags on a video with more "
                           f"than {YOUTUBE_IGNORE_ALL_ABOVE} (found {total}) — "
                           "platform rule"),
                "blocking": True,
            })
        backend = metadata.get("tags")
        if isinstance(backend, list) and any(
                str(t).lstrip().startswith("#") for t in backend):
            problems.append({
                "code": "metadata_tags_hashtags",
                "detail": "YouTube tags must be plain keywords without '#' — "
                          "hashtags belong in the description",
                "blocking": True,
            })
    elif platform in ("instagram", "tiktok"):
        below, above = caps["hashtag_min"], caps["hashtag_max"]
        if len(in_caption) > above:
            problems.append({
                "code": "hashtag_count",
                "detail": (f"{platform.capitalize()} caption allows at most "
                           f"{above} hashtags (found {len(in_caption)})"),
                "blocking": True,
            })
        if len(in_caption) < below:
            problems.append({
                "code": "hashtag_count",
                "detail": (f"{platform.capitalize()} discovery works best with "
                           f"{below}–{above} hashtags (found {len(in_caption)})"),
                "blocking": False,
            })
    else:  # facebook
        if len(in_caption) > caps["hashtag_max"]:
            problems.append({
                "code": "hashtag_count",
                "detail": (f"Facebook tolerates 0–{caps['hashtag_max']} hashtags "
                           f"(found {len(in_caption)}) — tag stuffing reads as spam"),
                "blocking": True,
            })
    return problems
