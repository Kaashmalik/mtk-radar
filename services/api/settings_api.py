"""Operator settings (v0.18, master plan §17 "configure publish windows in
settings"). A deliberately tiny keyed JSONB store:

  GET  /settings/{key}          → {key, value} (null when unset)
  PUT  /settings/{key}          → upsert {key, value, updated_by} (audited)

Known keys (validated on write):
  publish_windows → {"windows": ["18:00", "20:30"]}  — local PKT times the
  calendar defaults to and the scheduler suggests (default_publish_window).
"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import db
from api_hardening import effective_reviewer
from schedules_state import parse_publish_windows

router = APIRouter(prefix="/settings", tags=["settings"])

KNOWN_KEYS: dict[str, str] = {"publish_windows": "list of local (Asia/Karachi) HH:MM times"}


class SettingIn(BaseModel):
    value: Any


@router.get("/{key}")
async def get_setting(key: str) -> dict:
    pool = db.get()
    if key not in KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"unknown setting '{key}'")
    row = await pool.fetchrow("SELECT value::text AS value, updated_at FROM settings WHERE key = $1", key)
    if not row:
        return {"key": key, "value": None}
    return {"key": key, "value": json.loads(row["value"]), "updated_at": row["updated_at"]}


@router.put("/{key}", status_code=200)
async def put_setting(key: str, body: SettingIn, request: Request) -> dict:
    if key not in KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"unknown setting '{key}'")
    normalized = body.value
    if key == "publish_windows":
        try:
            normalized = {"windows": parse_publish_windows(body.value)}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    pool = db.get()
    updated_by = effective_reviewer(request, None, default="operator")
    await pool.execute(
        """
        INSERT INTO settings (key, value, updated_by) VALUES ($1, $2::jsonb, $3)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
            updated_by = EXCLUDED.updated_by, updated_at = now()
        """,
        key, json.dumps(normalized), updated_by,
    )
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, 'settings:update', 'settings', NULL, $2::jsonb)",
        updated_by, json.dumps({"key": key, "value": normalized}),
    )
    return {"key": key, "value": normalized, "updated_by": updated_by}
