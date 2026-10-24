"""Platform metadata, hashtags, CTA and A/B packaging (v0.27).

The old generator produced one safe caption. Professional publishing needs a
small, platform-aware copy system:

  * keyword-first titles within each platform limit
  * the operator's website link with campaign tracking (UTM)
  * a real CTA and a pinned comment
  * a broad/niche/branded hashtag mix (where the platform supports it)
  * English and Urdu variants
  * two title/hook options so the operator can run an experiment

The generator never invents offer facts. It only packages the verified fields
it is given, and every factual line can still be traced to evidence URLs.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

PLATFORMS: Final[tuple[str, ...]] = ("youtube", "facebook", "instagram", "tiktok")

PLATFORM_LIMITS: Final[dict[str, dict[str, int]]] = {
    "youtube": {"title": 100, "caption": 5000, "tags": 500},
    "facebook": {"title": 120, "caption": 5000, "tags": 0},
    "instagram": {"title": 0, "caption": 2200, "tags": 30},
    "tiktok": {"title": 0, "caption": 2200, "tags": 0},
}

_DEFAULT_HASHTAGS: Final[dict[str, tuple[str, ...]]] = {
    "broad": ("#free", "#offer", "#deal", "#save"),
    "student": ("#student", "#studentlife", "#studenthacks", "#education"),
    "developer": ("#developer", "#devtools", "#coding", "#programming"),
    "cloud": ("#cloud", "#hosting", "#devops", "#tech"),
    "ai": ("#ai", "#aitools", "#machinelearning", "#tech"),
    "domain": ("#domain", "#webdev", "#website", "#onlinetools"),
    "startup": ("#startup", "#founder", "#smallbusiness", "#growth"),
    "urdu": ("#اردو", "#پاکستان", "#ٹیکنالوجی", "#فری"),
}

#: Plain (no '#') YouTube search keywords per category — the broad, primary
#: tag first, as the 2026 packaging rules prescribe: tags play a minimal role
#: in discovery, so 5-8 well-chosen ones beat 30 hashtags.
_CATEGORY_KEYWORD: Final[dict[str, str]] = {
    "student_programs": "student discounts",
    "developer_tools": "developer tools",
    "model_hubs": "free ai models",
    "cloud_platforms": "cloud free tier",
    "domains_hosting": "free domain",
    "ai_tools": "ai tools",
    "education": "online learning",
    "startup_perks": "startup deals",
}

_DEFAULT_KEYWORD: Final = "free offers"

#: Keep YouTube titles within ~50 characters so the hook survives mobile
#: truncation; the 100-character platform ceiling stays a hard cap only.
YOUTUBE_TITLE_TARGET: Final = 50
YOUTUBE_TAG_TARGET: Final = (5, 8)

_CATEGORY_TAGS: Final[dict[str, str]] = {
    "student_programs": "student",
    "developer_tools": "developer",
    "model_hubs": "ai",
    "cloud_platforms": "cloud",
    "domains_hosting": "domain",
    "ai_tools": "ai",
    "education": "student",
    "startup_perks": "startup",
}

#: Title suffix is generated copy — it must match what the script format is
#: allowed to assert. Only `claim_walkthrough` may claim a performed, real
#: walkthrough; explainers/tutorials get wording that does not asset a result.
#: Unknown formats fall back to a neutral label, never a performed claim.
_TITLE_SUFFIX_BY_FORMAT = {
    "claim_walkthrough": {"en": "real claim walkthrough", "ur": "اصلی کلیم گائیڈ"},
    "official_explainer": {"en": "official terms explained", "ur": "آفیشل شرائط کی وضاحت"},
    "tested_tutorial": {"en": "tested tutorial", "ur": "آزمائش شدہ ٹیوٹوریل"},
}
_TITLE_SUFFIX_NEUTRAL = {"en": "walkthrough", "ur": "واک تھرو"}


def _title_suffix(language: str, format_hint: str | None) -> str:
    suffixes = (_TITLE_SUFFIX_BY_FORMAT.get(format_hint)
                if format_hint else None) or _TITLE_SUFFIX_NEUTRAL
    return suffixes.get(language, suffixes["en"])


_CTA = {
    "en": "Full guide, eligibility and source links are in the description.",
    "ur": "مکمل گائیڈ، اہلیت اور آفیشل لنکس ڈسکرپشن میں موجود ہیں۔",
}

_PINNED = {
    "en": "Pinned: official terms + full walkthrough → {url}",
    "ur": "پن شدہ: آفیشل شرائط اور مکمل گائیڈ → {url}",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def hashtagify(value: str) -> str:
    """Turn a provider/category phrase into a safe CamelCase hashtag."""
    words = re.findall(r"[A-Za-z0-9]+", value or "")
    if not words:
        return ""
    tag = "".join(word[:1].upper() + word[1:] for word in words[:4])
    return f"#{tag}" if len(tag) > 1 else ""


def build_hashtags(offer: dict[str, Any], platform: str, *,
                   language: str = "en", limit: int | None = None,
                   trend_keywords: list[str] | None = None,
                   performance: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Evidence-traceable hashtags within the platform's documented limits
    (v0.36 delegates to the hashtags.py capability table).

    Every tag cites its source (provider/category/trend/eligibility); nothing
    is invented. `trend_keywords` come from the trend row that produced the
    topic; `performance` is the `hashtag_production`-style feedback rollup.
    """
    import hashtags as hashtags_mod

    eligibility = offer.get("eligibility") if isinstance(offer.get("eligibility"), dict) else {}
    countries = eligibility.get("countries") if isinstance(eligibility.get("countries"), list) else []
    items = hashtags_mod.generate_hashtags(
        platform,
        provider=str(offer.get("provider") or ""),
        category=str(offer.get("category") or ""),
        title=str(offer.get("title") or ""),
        countries=[str(c) for c in countries],
        trend_keywords=trend_keywords,
        language=language,
        performance=performance,
    )
    tags = [item["tag"] for item in items]
    if limit is not None and len(tags) > limit:
        tags = tags[:limit]
    return tags


def youtube_category_keyword(category: str | None) -> str:
    """The one broad, primary search keyword for a category (no '#')."""
    return _CATEGORY_KEYWORD.get(str(category or "").lower(), _DEFAULT_KEYWORD)


def build_youtube_tags(offer: dict[str, Any], *,
                       language: str = "en",
                       channel_name: str | None = None) -> list[str]:
    """5-8 plain YouTube search tags: 1 broad + 2-4 specific + channel name.

    YouTube's own guidance is that tags play a minimal role in discovery and
    misleading tags are penalized. So: no '#'-prefixed hashtags (those belong
    in the description), no irrelevant keywords, never more than the tight
    target band, and every tag is derived from a verified offer field or the
    channel identity.
    """
    broad = youtube_category_keyword(offer.get("category"))
    specific: list[str] = []
    provider = _clean(offer.get("provider")).lower()
    if provider and len(provider) <= 40 and provider != broad:
        specific.append(provider)
    promo = _clean(offer.get("promo_code")).lower()
    if promo and re.fullmatch(r"[a-z0-9][a-z0-9-]*", promo) and promo not in broad:
        specific.append(promo)
    ordered: list[str] = [broad, f"{broad} 2026", *specific, "verified walkthrough"]
    if channel_name:
        channel = _clean(channel_name).lower()
        if channel and channel not in ordered:
            ordered.append(channel)
    # Pad from the category hashtag pool (stripped to plain keywords) to reach
    # the minimum of the band, then enforce the band ceiling.
    low, high = YOUTUBE_TAG_TARGET
    if len(ordered) < low:
        niche_key = _CATEGORY_TAGS.get(str(offer.get("category") or "").lower(), "broad")
        for tag in _DEFAULT_HASHTAGS.get(niche_key, ()):
            plain = tag.lstrip("#").lower()
            if plain and plain not in ordered:
                ordered.append(plain)
            if len(ordered) >= low:
                break
    seen: set[str] = set()
    out: list[str] = []
    total = 0
    for tag in ordered:
        normalized = _clean(tag).lower()
        if not normalized or normalized in seen:
            continue
        if total + len(normalized) + 1 > 500:
            break
        seen.add(normalized)
        out.append(normalized)
        total += len(normalized) + 1
        if len(out) >= high:
            break
    return out


def build_thumbnail_text(offer: dict[str, Any]) -> str:
    """Thumbnail wording: at most 3 words, never repeating the title verbatim.

    The thumbnail must be readable on a tiny phone screen, so it leads with a
    single specific verified fact (promo code, or the value amount with its
    currency) and never repeats the title text. Falls back to the generic
    verified badge when no specific fact survives the overlap filter.
    """
    title_words = set(re.findall(r"[a-z0-9]+", _clean(offer.get("title")).lower()))

    def fresh(candidate: str) -> str | None:
        words = _clean(candidate).split()
        if not words or len(words) > 3:
            return None
        lowered = [w.lower() for w in words]
        if any(word in title_words for word in lowered):
            return None
        return " ".join(words).upper()

    value = offer.get("value") if isinstance(offer.get("value"), dict) else {}
    amount = _clean(value.get("amount")) if isinstance(value, dict) else ""
    currency = _clean(value.get("currency")) if isinstance(value, dict) else ""
    candidates = [
        f"{amount} {currency}".strip() if amount and currency else "",
        _clean(offer.get("promo_code")),
        "verified claim",
        "walkthrough",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        fitted = fresh(candidate)
        if fitted:
            return fitted
    return "VERIFIED CLAIM"


def _fit_title(base: str, suffix: str, limit: int) -> str:
    """Trim a title to `limit` characters on a word boundary, suffix kept."""
    base = _clean(base)
    if len(base) + len(suffix) <= limit:
        return base + suffix
    words = base.split()
    budget = limit - len(suffix)
    while words and len(" ".join(words)) > budget:
        words.pop()
    trimmed = " ".join(words)
    if len(trimmed) >= 12:
        return trimmed + suffix
    # The base is unusably short once trimmed — ship the plain base instead of
    # a cryptic fragment.
    return base[:limit].rstrip()


def with_utm(url: str, *, platform: str, offer_id: Any, language: str = "en") -> str:
    """Attach campaign parameters without duplicating existing keys."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("utm_source", platform)
    query.setdefault("utm_medium", "video")
    query.setdefault("utm_campaign", "mtk_radar")
    query.setdefault("utm_content", f"{offer_id}-{language}")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _eligibility_lines(offer: dict[str, Any], language: str) -> list[str]:
    eligibility = offer.get("eligibility") if isinstance(offer.get("eligibility"), dict) else {}
    countries = eligibility.get("countries") or []
    lines: list[str] = []
    if countries:
        lines.append(("Region: " if language == "en" else "علاقہ: ") + ", ".join(countries))
    if eligibility.get("studentStatus"):
        lines.append("Students only (verification required)." if language == "en"
                     else "صرف طلبہ کے لیے (تصدیق ضروری ہے)۔")
    if eligibility.get("newCustomerOnly"):
        lines.append("New customers only." if language == "en" else "صرف نئے صارفین کے لیے۔")
    return lines


def _renewal_line(offer: dict[str, Any], language: str) -> str | None:
    renewal = offer.get("renewal") if isinstance(offer.get("renewal"), dict) else {}
    price = renewal.get("regularPrice")
    if not price:
        return None
    auto = " (auto-renew)" if renewal.get("autoRenew") else ""
    if language == "ur":
        return f"مفت مدت کے بعد قیمت {price}{' (خودکار تجدید)' if renewal.get('autoRenew') else ''} ہوگی۔"
    return f"After the free period this renews at {price}{auto}."


def build_metadata(
    platform: str,
    offer: dict[str, Any],
    evidence_urls: list[str] | None = None,
    disclosure: dict[str, Any] | None = None,
    correction_url: str | None = None,
    website_url: str | None = None,
    language: str = "en",
    variant: str = "default",
    hashtags: list[str] | None = None,
    channel_name: str | None = None,
    *,
    format_hint: str | None = None,
    trend_keywords: list[str] | None = None,
    hashtag_performance: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one platform/language metadata payload with hard limits."""
    if platform not in PLATFORMS:
        raise ValueError(f"unsupported platform '{platform}' — known: {', '.join(PLATFORMS)}")

    limits = PLATFORM_LIMITS[platform]
    disclosure = disclosure or {}
    title_base = _clean(offer.get("title") or "Offer walkthrough")
    suffix_en = f" — {_title_suffix(language, format_hint)}"
    title = f"{title_base}{suffix_en}"
    if variant == "b":
        title = ("Verified walkthrough: " if language == "en"
                 else "تصدیق شدہ واک تھرو: ") + title_base
    if platform == "youtube":
        # ~50-character mobile-safe titles; the 100-char platform ceiling is
        # only a last-resort guard.
        if variant == "b":
            title = _fit_title(title, "", YOUTUBE_TITLE_TARGET)
        else:
            title = _fit_title(title_base, suffix_en, YOUTUBE_TITLE_TARGET)
    if limits["title"]:
        title = title[: limits["title"]].rstrip()
    else:
        # TikTok/Instagram Reels have no separate title field; the first line of
        # the caption is the hook. Returning a title here leaks a field the
        # platform adapter would either drop or mis-post.
        title = ""

    provider = _clean(offer.get("provider"))
    lines: list[str] = []
    if language == "ur":
        lines.append(
            f"{provider} کی طرف سے {title_base} کا آفیشل واک تھرو۔ "
            "نتائج آپ کے اکاؤنٹ اور اہلیت پر منحصر ہیں۔"
        )
    else:
        # Never assert a generic "genuine end-to-end claim": an account-specific
        # walkthrough is not a promise that every viewer gets the same result (A13).
        lines.append(
            f"Official offer walkthrough: {title_base} by {provider}. "
            "Results depend on your account and eligibility."
        )
    eligibility_lines = _eligibility_lines(offer, language)
    if eligibility_lines:
        lines.extend(eligibility_lines)
    else:
        lines.append(
            "Eligibility not stated in the inspected terms — check the official "
            "terms for the current audience." if language == "en"
            else "اہلیت معائنہ شدہ شرائط میں درج نہیں — موجودہ سامعین کے لیے آفیشل شرائط دیکھیں۔"
        )
    renewal = _renewal_line(offer, language)
    if renewal:
        lines.append(renewal)
    else:
        lines.append(
            "Ongoing cost not stated in the inspected terms — unknown renewal is not free."
            if language == "en"
            else "جاری قیمت معائنہ شدہ شرائط میں درج نہیں — نامعلوم تجدید مفت نہیں ہے۔"
        )
    if disclosure.get("synthetic_narration"):
        lines.append("Narration is AI-generated (disclosed per platform policy)." if language == "en"
                     else "آواز AI سے تیار کی گئی ہے (پلیٹ فارم پالیسی کے مطابق ظاہر کیا گیا)۔")

    tracked_site = with_utm(website_url or "", platform=platform,
                            offer_id=offer.get("id", "offer"), language=language)
    if tracked_site:
        lines.append(("Website / full guide: " if language == "en" else "ویب سائٹ / مکمل گائیڈ: ") + tracked_site)
    if correction_url:
        lines.append(("Corrections & updates: " if language == "en" else "تصحیح اور اپ ڈیٹس: ") + correction_url)

    desc_hashtags: list[str] = []
    if platform == "youtube":
        # Plain 5–8 backend keywords; hashtags ride the DESCRIPTION tail
        # (the first 3 render above the title), never the `tags` field.
        if hashtags is not None:
            desc_hashtags = [str(t) for t in hashtags]
            tags = [str(t).lstrip("#").lower() for t in hashtags]
        else:
            desc_hashtags = build_hashtags(
                offer, platform, language=language,
                trend_keywords=trend_keywords, performance=hashtag_performance)
            tags = build_youtube_tags(offer, language=language,
                                      channel_name=channel_name)
    else:
        tags = hashtags if hashtags is not None else build_hashtags(
            offer, platform, language=language,
            trend_keywords=trend_keywords, performance=hashtag_performance)
    # Hashtag placement (v0.36, WP-E capability table): YouTube in the
    # description tail, TikTok in the caption, Instagram as the caption tail;
    # Facebook only ever sees the 0–2 the capability table allows.
    if desc_hashtags:
        lines.append(" ".join(desc_hashtags[:5]))
    if tags and platform in ("instagram", "tiktok", "facebook"):
        lines.append(" ".join(tags[:3] if platform != "facebook" else tags[:2]))
    if evidence_urls:
        lines.append("Sources & terms (may change):" if language == "en" else "ذرائع اور شرائط (بدل سکتے ہیں):")
        lines.extend(f"- {u}" for u in evidence_urls[:3])

    caption = "\n".join(lines)
    if len(caption) > limits["caption"]:
        caption = caption[: limits["caption"] - 1].rstrip() + "…"

    pinned = _PINNED.get(language, _PINNED["en"]).format(url=tracked_site or "[website]")
    return {
        "platform": platform,
        "language": language,
        "variant": variant,
        "title": title,
        "caption": caption,
        "tags": tags if limits["tags"] else [],
        "hashtags": desc_hashtags if platform == "youtube" else tags,
        "website_url": tracked_site,
        "cta": _CTA.get(language, _CTA["en"]),
        "pinned_comment": pinned,
        "privacy_default": "private",
    }


def build_variants(platform: str, offer: dict[str, Any], *,
                   evidence_urls: list[str] | None = None,
                   disclosure: dict[str, Any] | None = None,
                   correction_url: str | None = None,
                   website_url: str | None = None,
                   language: str = "en",
                   format_hint: str | None = None,
                   channel_name: str | None = None) -> list[dict[str, Any]]:
    """Two reviewable packaging options (A/B) for experimentation."""
    return [
        build_metadata(platform, offer, evidence_urls, disclosure, correction_url,
                       website_url, language, variant="default",
                       format_hint=format_hint, channel_name=channel_name),
        build_metadata(platform, offer, evidence_urls, disclosure, correction_url,
                       website_url, language, variant="b",
                       format_hint=format_hint, channel_name=channel_name),
    ]


def metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    """Compact preview for dashboards (never leak raw provider secrets)."""
    return {
        "title": metadata.get("title", ""),
        "caption": metadata.get("caption", ""),
        "tags": metadata.get("tags", []),
        "hashtags": metadata.get("hashtags", []),
        "website_url": metadata.get("website_url", ""),
        "pinned_comment": metadata.get("pinned_comment", ""),
        "language": metadata.get("language", "en"),
        "platform": metadata.get("platform", ""),
        "cta": metadata.get("cta", ""),
    }
