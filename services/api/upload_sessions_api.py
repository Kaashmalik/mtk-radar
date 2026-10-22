"""Persisted resumable-upload sessions (v0.31).

The publishing worker owns the provider session URI; the dashboard must never
see it. Only service/worker credentials may create, read, advance or clear a
session. A row is short-lived and deleted as soon as the upload completes or a
human reconciles the schedule.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

import db
from api_hardening import CREDENTIAL_SERVICE, CREDENTIAL_WORKER, credential_class

router = APIRouter(tags=["publishing"])

SESSION_TTL_HOURS = 2
ALLOWED_URI_PREFIXES = (
    "https://www.googleapis.com/upload/youtube/v3/",
    "https://upload.youtube.com/",
)


class UploadSessionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_uri: str = Field(strict=True, min_length=20, max_length=4096)
    content_length: int = Field(strict=True, ge=0)
    provider: Literal["youtube"] = "youtube"

    @field_validator("session_uri")
    @classmethod
    def official_provider_uri(cls, value: str) -> str:
        if not value.startswith(ALLOWED_URI_PREFIXES):
            raise ValueError("upload session URI must be a YouTube resumable endpoint")
        return value


class UploadProgressIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bytes_sent: int = Field(strict=True, ge=0)


def _worker_only(request: Request) -> None:
    if credential_class(request) not in (CREDENTIAL_SERVICE, CREDENTIAL_WORKER):
        raise HTTPException(
            status_code=403,
            detail="resumable upload sessions are restricted to service/worker credentials",
        )


def _payload(row) -> dict:
    return {
        "schedule_id": str(row["schedule_id"]),
        "provider": row["provider"],
        "session_uri": row["session_uri"],
        "content_length": row["content_length"],
        "bytes_sent": row["bytes_sent"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "expires_at": row["expires_at"].isoformat(),
    }


@router.get("/schedules/{schedule_id}/upload-session")
async def get_upload_session(schedule_id: uuid.UUID, request: Request) -> dict:
    _worker_only(request)
    pool = db.get()
    row = await pool.fetchrow(
        """
        SELECT schedule_id, provider, session_uri, content_length, bytes_sent,
               created_at, updated_at, expires_at
        FROM upload_sessions
        WHERE schedule_id = $1 AND expires_at > now()
        """,
        schedule_id,
    )
    if not row:
        # Expired-but-still-present rows are deliberately removed so a later
        # attempt cannot resume against a dead capability.
        await pool.execute("DELETE FROM upload_sessions WHERE schedule_id = $1", schedule_id)
        raise HTTPException(status_code=404, detail="no active upload session")
    return _payload(row)


@router.put("/schedules/{schedule_id}/upload-session")
async def save_upload_session(
    schedule_id: uuid.UUID, body: UploadSessionIn, request: Request,
) -> dict:
    _worker_only(request)
    pool = db.get()
    exists = await pool.fetchval("SELECT 1 FROM schedules WHERE id = $1", schedule_id)
    if not exists:
        raise HTTPException(status_code=404, detail="schedule not found")
    row = await pool.fetchrow(
        """
        INSERT INTO upload_sessions
            (schedule_id, provider, session_uri, content_length, bytes_sent,
             expires_at)
        VALUES ($1, $2, $3, $4, 0, now() + make_interval(hours => $5))
        ON CONFLICT (schedule_id) DO UPDATE
        SET provider = EXCLUDED.provider,
            session_uri = EXCLUDED.session_uri,
            content_length = EXCLUDED.content_length,
            bytes_sent = 0,
            created_at = now(),
            updated_at = now(),
            expires_at = EXCLUDED.expires_at
        RETURNING schedule_id, provider, session_uri, content_length, bytes_sent,
                  created_at, updated_at, expires_at
        """,
        schedule_id, body.provider, body.session_uri, body.content_length,
        SESSION_TTL_HOURS,
    )
    return _payload(row)


@router.patch("/schedules/{schedule_id}/upload-session")
async def record_upload_progress(
    schedule_id: uuid.UUID, body: UploadProgressIn, request: Request,
) -> dict:
    _worker_only(request)
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE upload_sessions
        SET bytes_sent = $2, updated_at = now()
        WHERE schedule_id = $1 AND expires_at > now()
          AND $2 <= content_length
        RETURNING schedule_id, provider, session_uri, content_length, bytes_sent,
                  created_at, updated_at, expires_at
        """,
        schedule_id, body.bytes_sent,
    )
    if not row:
        content_length = await pool.fetchval(
            "SELECT content_length FROM upload_sessions "
            "WHERE schedule_id = $1 AND expires_at > now()",
            schedule_id,
        )
        if content_length is None:
            raise HTTPException(status_code=404, detail="no active upload session")
        raise HTTPException(
            status_code=422,
            detail=f"bytes_sent exceeds content_length ({content_length})",
        )
    return _payload(row)


@router.delete("/schedules/{schedule_id}/upload-session", status_code=204)
async def clear_upload_session(schedule_id: uuid.UUID, request: Request) -> None:
    # The sweep lock permits one publisher per schedule, so clearing by schedule
    # is sufficient. Never put the capability-bearing URI in a URL/query string:
    # proxies and access logs would record it.
    _worker_only(request)
    await db.get().execute(
        "DELETE FROM upload_sessions WHERE schedule_id = $1", schedule_id,
    )
