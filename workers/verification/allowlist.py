"""Provider-domain allowlist checks (master plan §3).

"Check that the source belongs to the provider (domain and account handle)"
— evidence URLs outside the registered official domains can never be marked
official, no matter what the caller claims.
"""

from urllib.parse import urlsplit


def build_allowlist(sources: list[dict]) -> dict[str, dict]:
    """Group the source registry by provider (case-insensitive):
    provider → {"domains": {...}, "handles": {...}, "source_ids": [...]}"""
    allowlist: dict[str, dict] = {}
    for source in sources:
        if not source.get("enabled") or source.get("trust_tier") != "A_provider_owned":
            continue
        key = (source.get("provider") or "").strip().lower()
        if not key:
            continue
        entry = allowlist.setdefault(key, {"domains": set(), "handles": set(), "source_ids": []})
        if source.get("canonical_domain"):
            entry["domains"].add(source["canonical_domain"].lower())
        if source.get("account_handle"):
            entry["handles"].add(source["account_handle"].lower())
        entry["source_ids"].append(source["id"])
    return allowlist


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def domain_ok(allowlist: dict[str, dict], provider: str, url: str) -> bool:
    """True when the URL host is the provider's canonical domain or a
    subdomain of it."""
    entry = allowlist.get((provider or "").strip().lower())
    if not entry or not entry["domains"]:
        return False
    host = host_of(url)
    if not host:
        return False
    for domain in entry["domains"]:
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False


def official_sources_for(allowlist: dict[str, dict], provider: str) -> list[dict]:
    """All registered sources of the provider that can produce official evidence."""
    entry = allowlist.get((provider or "").strip().lower())
    if not entry or not entry["domains"]:
        return []
    return entry["source_ids"]
