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
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
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
async def list_accounts(platform: Optional[str] = None) -> list[dict]:
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT id, platform, account_handle, credential_source, scopes, status,
               expires_at, last_refreshed_at, last_error, created_at, updated_at
        FROM platform_accounts
        WHERE ($1::text IS NULL OR platform = $1)
        ORDER BY platform, account_handle
        """,
        platform,
    )
    return [dict(r) for r in rows]


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
