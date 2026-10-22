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

_TITLE_SUFFIX = {
    "en": "real claim walkthrough",
    "ur": "اصلی کلیم گائیڈ",
}

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
                   language: str = "en", limit: int | None = None) -> list[str]:
    """Broad + niche + provider + regional hashtags, deduplicated."""
    category = str(offer.get("category") or "").lower()
    niche_key = _CATEGORY_TAGS.get(category, "broad")
    tags: list[str] = []
    tags.extend(_DEFAULT_HASHTAGS.get("broad", ()))
    tags.extend(_DEFAULT_HASHTAGS.get(niche_key, ()))
    provider_tag = hashtagify(str(offer.get("provider") or ""))
    if provider_tag:
        tags.append(provider_tag)
    if language == "ur":
        tags.extend(_DEFAULT_HASHTAGS["urdu"])
    countries = offer.get("eligibility", {}).get("countries") if isinstance(offer.get("eligibility"), dict) else None
    if countries:
        tags.append(hashtagify(str(countries[0])))
    # Platform-specific ceiling. YouTube has a character cap rather than a tag
    # count, so callers pass a conservative count (30) and the adapter truncates.
    ceiling = limit if limit is not None else (
        30 if platform == "instagram" else 12 if platform == "tiktok" else 15
    )
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        normalized = tag.strip()
        if not normalized or normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        out.append(normalized)
        if len(out) >= ceiling:
            break
    return out


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
) -> dict[str, Any]:
    """Build one platform/language metadata payload with hard limits."""
    if platform not in PLATFORMS:
        raise ValueError(f"unsupported platform '{platform}' — known: {', '.join(PLATFORMS)}")

    limits = PLATFORM_LIMITS[platform]
    disclosure = disclosure or {}
    title_base = _clean(offer.get("title") or "Offer walkthrough")
    suffix = _TITLE_SUFFIX.get(language, _TITLE_SUFFIX["en"])
    title = f"{title_base} — {suffix}"
    if variant == "b":
        title = ("Verified walkthrough: " if language == "en"
                 else "تصدیق شدہ واک تھرو: ") + title_base
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

    tags = hashtags if hashtags is not None else build_hashtags(offer, platform, language=language)
    if tags and platform in ("instagram", "tiktok"):
        lines.append(" ".join(tags))
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
        "hashtags": tags,
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
                   language: str = "en") -> list[dict[str, Any]]:
    """Two reviewable packaging options (A/B) for experimentation."""
    return [
        build_metadata(platform, offer, evidence_urls, disclosure, correction_url,
                       website_url, language, variant="default"),
        build_metadata(platform, offer, evidence_urls, disclosure, correction_url,
                       website_url, language, variant="b"),
    ]


def metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    """Compact preview for dashboards (never leak raw provider secrets)."""
    return {
        "title": metadata.get("title", ""),
        "caption": metadata.get("caption", ""),
        "hashtags": metadata.get("hashtags", []),
        "website_url": metadata.get("website_url", ""),
        "pinned_comment": metadata.get("pinned_comment", ""),
        "language": metadata.get("language", "en"),
        "platform": metadata.get("platform", ""),
        "cta": metadata.get("cta", ""),
    }
