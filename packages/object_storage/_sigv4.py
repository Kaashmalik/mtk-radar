"""AWS Signature Version 4 (SigV4) — request signing for S3-compatible stores.

Hand-rolled (zero-dep, httpx transport) because SigV4 has been frozen by AWS
since 2015 and is verified against the published test vectors in
tests/test_sigv4.py. Works with AWS S3, MinIO, Cloudflare R2, Backblaze B2 —
anything speaking the S3 protocol.

Reference: https://docs.aws.amazon.com/general/latest/gr/sigv4-calculate-signature.html
"""

import hashlib
import hmac
import urllib.parse
from datetime import datetime, timezone
from typing import Any

EMPTY_PAYLOAD_SHA256 = hashlib.sha256(b"").hexdigest()
ALGORITHM = "AWS4-HMAC-SHA256"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret_key: str, datestamp: str, region: str, service: str) -> bytes:
    """kSigning = HMAC(HMAC(HMAC(HMAC("AWS4"+secret, date), region), service), "aws4_request")."""
    k = _hmac(f"AWS4{secret_key}".encode("utf-8"), datestamp)
    k = _hmac(k, region)
    k = _hmac(k, service)
    return _hmac(k, "aws4_request")


def amz_date(now: datetime | None = None) -> str:
    """ISO8601 basic format: 20150830T123600Z."""
    dt = now or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _uri_encode(value: str, encode_slash: bool = True) -> str:
    """AWS's strict RFC3986 set: unreserved = A-Z a-z 0-9 - _ . ~"""
    safe = "-_.~" if encode_slash else "-_.~/"
    return urllib.parse.quote(value, safe=safe)


def _canonical_query(params: dict[str, Any] | None) -> str:
    if not params:
        return ""
    # AWS: URI-encode name/value once, sort by encoded name then value
    pairs = sorted(
        (_uri_encode(str(k)), _uri_encode(str(v)))
        for k, v in params.items()
    )
    return "&".join(f"{k}={v}" for k, v in pairs)


def _canonical_headers(headers: dict[str, str]) -> tuple[str, str]:
    """Returns (canonical header block, semicolon-sorted signed header names)."""
    lowered = {k.lower().strip(): " ".join(str(v).split()) for k, v in headers.items()}
    names = sorted(lowered)
    block = "".join(f"{n}:{lowered[n]}\n" for n in names)
    return block, ";".join(names)


def canonical_request(
    method: str,
    path: str,
    query: str,
    headers: dict[str, str],
    payload_hash: str,
) -> tuple[str, str]:
    """Returns (canonical request text, signed header list)."""
    canon_path = _uri_encode(path, encode_slash=False) or "/"
    hdr_block, signed = _canonical_headers(headers)
    creq = "\n".join([method.upper(), canon_path, query, hdr_block, signed, payload_hash])
    return creq, signed


def string_to_sign(amzdate: str, scope: str, creq: str) -> str:
    return "\n".join([
        ALGORITHM,
        amzdate,
        scope,
        sha256_hex(creq.encode("utf-8")),
    ])


def scope_of(datestamp: str, region: str, service: str) -> str:
    return f"{datestamp}/{region}/{service}/aws4_request"


def signature(signing_key_bytes: bytes, sts: str) -> str:
    return hmac.new(signing_key_bytes, sts.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_request(
    *,
    method: str,
    url_path: str,
    query: dict[str, Any] | None,
    headers: dict[str, str],
    payload_hash: str,
    access_key: str,
    secret_key: str,
    region: str,
    service: str,
    now: datetime | None = None,
) -> dict[str, str]:
    """Returns `headers` augmented with x-amz-date, x-amz-content-sha256 (S3
    callers pass it in) and the Authorization header.

    `headers` MUST already contain a `Host` value (httpx sets it from the URL,
    but signing happens pre-flight, so callers pass it explicitly).
    """
    dt = now or datetime.now(timezone.utc)
    dt = dt.astimezone(timezone.utc)
    amzdate = dt.strftime("%Y%m%dT%H%M%SZ")
    datestamp = dt.strftime("%Y%m%d")

    headers = {**headers, "x-amz-date": amzdate}
    headers.setdefault("x-amz-content-sha256", payload_hash)

    query_str = _canonical_query(query)
    creq, signed = canonical_request(method, url_path, query_str, headers, payload_hash)
    sc = scope_of(datestamp, region, service)
    sts = string_to_sign(amzdate, sc, creq)
    key = signing_key(secret_key, datestamp, region, service)
    sig = signature(key, sts)

    headers["Authorization"] = (
        f"{ALGORITHM} Credential={access_key}/{sc}, "
        f"SignedHeaders={signed}, Signature={sig}"
    )
    return headers


def parse_s3_ref(ref: str) -> tuple[str, str]:
    """'s3://bucket/some/key.mp4' → (bucket, 'some/key.mp4')."""
    if not ref.startswith("s3://"):
        raise ValueError(f"not an s3 ref: {ref!r}")
    rest = ref[5:]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"malformed s3 ref (want s3://bucket/key): {ref!r}")
    return bucket, key


def object_url_encode(key: str) -> str:
    """Encode each key segment, preserving '/'. AWS strict set."""
    return "/".join(_uri_encode(seg) for seg in key.split("/"))
