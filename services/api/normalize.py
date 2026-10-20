"""URL canonicalization and content hashing for deduplication.

Best practice (master plan §10/§18): a candidate appears EXACTLY ONCE with a
canonical URL, timestamp, and deduplication key — regardless of which source
(or the extension) observed it first.
"""

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Common tracking parameters that make identical pages look different.
TRACKING_PARAMS = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "ref", "ref_src", "fbclid", "gclid", "igshid", "igsh", "mc_cid",
        "mc_eid", "yclid", "_ga", "si",
    }
)

_UPPER_HOST_RE = re.compile(r"^(www\d?)\.")


def canonicalize_url(url: str) -> str:
    """Normalize a URL so identical pages collapse to one candidate.

    - lowercase scheme + host, drop default ports, strip 'www.'
    - drop fragment and tracking params
    - strip trailing slash (except root path)
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    host = (parts.hostname or "").lower()
    host = _UPPER_HOST_RE.sub("", host)

    # IPv6 or missing host → keep netloc as-is.
    if not host and parts.netloc:
        host = parts.netloc.lower()

    netloc = host
    if parts.port and not ((scheme == "http" and parts.port == 80) or (scheme == "https" and parts.port == 443)):
        netloc = f"{host}:{parts.port}" if host else parts.netloc

    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"

    filtered = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(filtered, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_text(*parts: str | None) -> str:
    """Collapse whitespace so trivial formatting differences hash the same."""
    joined = " ".join(p for p in parts if p)
    return re.sub(r"\s+", " ", joined).strip().lower()


def hash_parts(*parts: str | None) -> str:
    return hashlib.sha256(normalize_text(*parts).encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    return hash_parts(text)
