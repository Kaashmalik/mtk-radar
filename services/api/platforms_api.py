"""Platform accounts router — credential references + token-expiry recovery
(week 10, master plan §6).

RULE: raw tokens are NEVER accepted or stored here. `credential_source` holds
a REFERENCE ('env:YOUTUBE_*' or 'vault:<path>'); adapters keep tokens in
memory only. Token expiry is reported by the publishing worker and surfaced
to the operator — recovery = operator updates the vault/env, worker refreshes
on next sweep, accounts return to 'active'.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

import db

router = APIRouter(tags=["platform-accounts"])

PLATFORMS = ("youtube", "facebook", "instagram", "tiktok")


class PlatformAccountIn(BaseModel):
    platform: str
    account_handle: str = Field(min_length=1)
    credential_source: str = Field(min_length=3, pattern=r"^(env:[A-Z0-9_]+|vault:.+)$")
    scopes: list[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None


class MarkExpiredIn(BaseModel):
    detail: Optional[str] = None


class RefreshedIn(BaseModel):
    expires_at: datetime


#: Fields the worker may publish from TikTok creator_info. An allowlist, so a
#: provider payload can never smuggle tokens or unrelated data into the DB.
_TIKTOK_CAPABILITY_FIELDS = (
    "creator_username", "creator_nickname", "creator_avatar_url",
    "privacy_level_options", "comment_disabled", "duet_disabled",
    "stitch_disabled", "max_video_post_duration_sec",
)


class CapabilitiesIn(BaseModel):
    capabilities: dict = Field(default_factory=dict)


def sanitize_capabilities(platform: str, raw: dict) -> dict:
    """Keep only known, size-bounded capability fields."""
    if platform != "tiktok":
        return {}
    out: dict = {}
    for key in _TIKTOK_CAPABILITY_FIELDS:
        value = raw.get(key)
        if value is None:
            continue
        if key == "privacy_level_options":
            if isinstance(value, list):
                out[key] = [str(v)[:40] for v in value[:10]]
        elif key.endswith("_disabled"):
            out[key] = bool(value)
        elif key == "max_video_post_duration_sec":
            try:
                out[key] = max(0, int(value))
            except (TypeError, ValueError):
                continue
        else:
            out[key] = str(value)[:300]
    return out


@router.post("/platform-accounts", status_code=201)
async def register_account(account: PlatformAccountIn) -> dict:
    """Register/refresh credential REFERENCES. Idempotent per platform+handle."""
    pool = db.get()
    if account.platform not in PLATFORMS:
        raise HTTPException(status_code=400,
                            detail=f"unsupported platform — known: {', '.join(PLATFORMS)}")
    if "token" in account.credential_source.lower() and "env:" not in account.credential_source:
        raise HTTPException(status_code=422,
                            detail="do not reference token material — register a vault path or env prefix")

    row = await pool.fetchrow(
        """
        INSERT INTO platform_accounts (platform, account_handle, credential_source,
                                       scopes, expires_at, last_refreshed_at)
        VALUES ($1, $2, $3, $4, $5, CASE WHEN $5 IS NULL THEN NULL ELSE now() END)
        ON CONFLICT (platform, account_handle) DO UPDATE
        SET credential_source = EXCLUDED.credential_source,
            scopes = EXCLUDED.scopes,
            expires_at = EXCLUDED.expires_at,
            status = 'active',
            last_error = NULL,
            updated_at = now()
        RETURNING id, (xmax = 0) AS inserted
        """,
        account.platform, account.account_handle, account.credential_source,
        account.scopes, account.expires_at,
    )
    return {"id": row["id"], "created": bool(row["inserted"]), "status": "active"}


@router.get("/platform-accounts")
async def list_accounts(
    response: Response,
    platform: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    cursor: Optional[str] = Query(default=None),
) -> list[dict]:
    pool = db.get()
    from pagination import (
        decode_cursor,
        decode_uuid,
        encode_cursor,
        set_next_cursor,
    )
    parts = decode_cursor(cursor, 3)
    before_platform = parts[0] if parts else None
    before_handle = parts[1] if parts else None
    before_id = decode_uuid(parts[2]) if parts else None
    rows = await pool.fetch(
        """
        SELECT id, platform, account_handle, credential_source, scopes, status,
               capabilities::text AS capabilities, capabilities_checked_at,
               expires_at, last_refreshed_at, last_error, created_at, updated_at
        FROM platform_accounts
        WHERE ($1::text IS NULL OR platform = $1)
          AND ($3::text IS NULL
               OR (platform, account_handle, id) < ($3::text, $4::text, $5::uuid))
        ORDER BY platform, account_handle, id
        LIMIT $2
        """,
        platform, limit, before_platform, before_handle, before_id,
    )
    out = [dict(r) for r in rows]
    for row in out:
        try:
            row["capabilities"] = json.loads(row.get("capabilities") or "{}")
        except ValueError:
            row["capabilities"] = {}
    set_next_cursor(
        response, out, limit,
        lambda row: encode_cursor(row["platform"], row["account_handle"], row["id"]),
    )
    return out


@router.post("/platform-accounts/{account_id}/test")
async def test_connection(account_id: uuid.UUID) -> dict:
    """Credential metadata check for a stored account (dashboard 'Test' button).

    This is deliberately NOT a live API call: the API holds only credential
    REFERENCES (never tokens), so it cannot reach the provider on its own.
    What it CAN verify honestly is the recorded metadata: the reference must
    exist, scopes must cover the platform's required scopes, and a recorded
    expiry must not be in the past. Failures update `last_error` on the
    account so the connections page explains itself.
    """
    pool = db.get()
    row = await pool.fetchrow(
        """
        SELECT id, platform, account_handle, credential_source, scopes::text[] AS scopes,
               status, expires_at FROM platform_accounts WHERE id = $1
        """,
        account_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="account not found")
    scopes = list(row["scopes"] or [])
    required = {
        "youtube": ["youtube.upload", "yt-analytics.readonly"],
    }.get(row["platform"], [])
    problems = []
    if not row["credential_source"]:
        problems.append("no credential reference recorded")
    if row["status"] == "revoked":
        problems.append("credential is revoked")
    missing = [s for s in required if not any(s in str(x) for x in scopes)]
    if missing:
        problems.append(
            "recorded scopes are missing: " + ", ".join(missing)
            + " (update the reference or record the granted scopes)")
    if row["expires_at"] and row["expires_at"] <= datetime.now(timezone.utc):
        problems.append("recorded token expiry is in the past — refresh or re-auth")
    ok = not problems
    await pool.execute(
        "UPDATE platform_accounts SET last_error = $2, updated_at = now() WHERE id = $1",
        account_id, None if ok else "; ".join(problems),
    )
    return {
        "id": str(account_id),
        "platform": row["platform"],
        "ok": ok,
        "problems": problems,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "note": ("credential metadata checked; a live provider call requires "
                 "the worker holding the actual token"),
    }


@router.post("/platform-accounts/{account_id}/mark-expired")
async def mark_expired(account_id: uuid.UUID, body: MarkExpiredIn) -> dict:
    """Publishing worker reports a dead session → operator-visible alert state."""
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE platform_accounts
        SET status = 'token_expired', last_error = $2, updated_at = now()
        WHERE id = $1
        RETURNING id, platform, account_handle, status
        """,
        account_id, body.detail,
    )
    if not row:
        raise HTTPException(status_code=404, detail="account not found")
    await _audit(pool, action="platform_account:token_expired", entity_id=account_id.__str__(),
                 detail={"platform": row["platform"], "reason": body.detail})
    return {"id": row["id"], "status": row["status"]}


@router.post("/platform-accounts/{account_id}/refreshed")
async def mark_refreshed(account_id: uuid.UUID, body: RefreshedIn) -> dict:
    """Worker reports a successful in-memory refresh (expiry only, no token)."""
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE platform_accounts
        SET status = 'active', expires_at = $2, last_refreshed_at = now(),
            last_error = NULL, updated_at = now()
        WHERE id = $1
        RETURNING id, status
        """,
        account_id, body.expires_at,
    )
    if not row:
        raise HTTPException(status_code=404, detail="account not found")
    return {"id": row["id"], "status": row["status"]}


@router.put("/platform-accounts/{account_id}/capabilities")
async def set_capabilities(account_id: uuid.UUID, body: CapabilitiesIn) -> dict:
    """Publishing worker publishes the account's live capability snapshot
    (TikTok creator_info). Allowlisted fields only; never credentials."""
    pool = db.get()
    platform = await pool.fetchval(
        "SELECT platform FROM platform_accounts WHERE id = $1", account_id)
    if platform is None:
        raise HTTPException(status_code=404, detail="account not found")
    clean = sanitize_capabilities(platform, body.capabilities)
    await pool.execute(
        "UPDATE platform_accounts SET capabilities = $2::jsonb, "
        "capabilities_checked_at = now(), updated_at = now() WHERE id = $1",
        account_id, json.dumps(clean),
    )
    return {"id": str(account_id), "capabilities": clean}


@router.post("/platform-accounts/{account_id}/revoke")
async def revoke(account_id: uuid.UUID) -> dict:
    pool = db.get()
    row = await pool.fetchrow(
        "UPDATE platform_accounts SET status = 'revoked', updated_at = now() WHERE id = $1 "
        "RETURNING id, status",
        account_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="account not found")
    await _audit(pool, action="platform_account:revoked", entity_id=str(account_id))
    return {"id": row["id"], "status": row["status"]}


async def _audit(pool, *, action: str, entity_id: str, detail: Optional[dict] = None) -> None:
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "worker", action, "platform_accounts", uuid.UUID(entity_id) if entity_id else None,
        json.dumps(detail or {}, default=str),
    )
