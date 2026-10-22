"""Automation policy API (v0.26).

Read/write the operator's human-vs-automation policy, inspect live guardrail
usage and the automation work queue, and flip the global kill switch.

    GET  /automation/policy        effective policy + presets + summary
    PUT  /automation/policy        validated partial/full update (audited)
    POST /automation/preset/{name} apply manual | assisted | autopilot
    POST /automation/pause         stop every automation writer immediately
    POST /automation/resume        resume the configured stages
    GET  /automation/status        budget, queues, recent automation actions
    GET  /automation/next-slot     next publish slot for a platform

APIs are authoritative: workers may only perform a gated action when the
policy says ``auto`` AND their actor is ``automation:<stage>``. The routers
re-check that on every write, so these endpoints only make the contract
visible — they do not grant it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

import db
from api_hardening import effective_reviewer
from automation import (
    POLICY_KEY,
    PolicyError,
    default_policy,
    describe,
    guardrails,
    list_presets,
    normalize_policy,
    preset_policy,
)
from schedules_state import default_publish_window, parse_publish_windows
from settings_store import audit, get_value, put_value

router = APIRouter(prefix="/automation", tags=["automation"])

PRESET_NAMES = ("manual", "assisted", "autopilot")


class PolicyIn(BaseModel):
    policy: dict[str, Any]


class PauseIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


async def load_policy() -> dict[str, Any]:
    """Read + validate the stored policy. A corrupt/missing row falls back to
    the safe assisted default (never to autopilot)."""
    stored = await get_value(db.get(), POLICY_KEY)
    if not stored:
        return default_policy()
    try:
        return normalize_policy(stored["value"])
    except (PolicyError, ValueError):
        return default_policy()


async def save_policy(policy: dict[str, Any], *, actor: str,
                      action: str = "automation:policy-update",
                      detail: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    pool = db.get()
    await put_value(pool, POLICY_KEY, policy, updated_by=actor)
    await audit(pool, actor=actor, action=action, entity="settings",
                detail={"key": POLICY_KEY, "mode": policy.get("mode"),
                        "paused": policy.get("paused"),
                        "stages": policy.get("stages"),
                        **(detail or {})})
    return policy


async def _budget_used(pool) -> int:
    """Schedules approved/scheduled by automation today (server-side budget)."""
    return int(await pool.fetchval(
        """
        SELECT COUNT(*) FROM schedules
        WHERE approved_by LIKE 'automation:%'
          AND updated_at >= date_trunc('day', now())
        """
    ) or 0)


@router.get("/policy")
async def get_policy() -> dict[str, Any]:
    stored = await get_value(db.get(), POLICY_KEY)
    policy = await load_policy()
    return {
        "key": POLICY_KEY,
        "policy": policy,
        "summary": describe(policy),
        "presets": list_presets(),
        "updated_at": stored.get("updated_at") if stored else None,
        "updated_by": stored.get("updated_by") if stored else None,
    }


@router.put("/policy")
async def put_policy(body: PolicyIn, request: Request) -> dict[str, Any]:
    current = await load_policy()
    try:
        policy = normalize_policy(body.policy, base=current)
    except PolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    actor = effective_reviewer(request, None, default="operator")
    await save_policy(policy, actor=actor, action="automation:policy-update")
    return {"policy": policy, "summary": describe(policy)}


@router.post("/preset/{name}")
async def apply_preset(name: str, request: Request) -> dict[str, Any]:
    if name not in PRESET_NAMES:
        raise HTTPException(
            status_code=404,
            detail=f"unknown preset '{name}' — known: {', '.join(PRESET_NAMES)}",
        )
    policy = preset_policy(name)
    # Changing the mode must never silently unpause a deliberate kill switch
    # or clear dry-run; those are separate, explicit operator actions.
    current = await load_policy()
    policy["paused"] = bool(current.get("paused", False))
    policy["dry_run"] = bool(current.get("dry_run", False))
    actor = effective_reviewer(request, None, default="operator")
    await save_policy(policy, actor=actor, action=f"automation:preset:{name}")
    return {"policy": policy, "summary": describe(policy)}


@router.post("/pause")
async def pause_automation(request: Request, body: Optional[PauseIn] = None) -> dict[str, Any]:
    """Global kill switch. Scheduled posts already approved are NOT cancelled;
    they are simply not auto-advanced. A human can still act."""
    policy = await load_policy()
    policy["paused"] = True
    actor = effective_reviewer(request, None, default="operator")
    await save_policy(policy, actor=actor, action="automation:pause",
                      detail={"note": (body.note if body else None)})
    return {"policy": policy, "summary": describe(policy)}


@router.post("/resume")
async def resume_automation(request: Request) -> dict[str, Any]:
    policy = await load_policy()
    policy["paused"] = False
    policy["dry_run"] = False
    actor = effective_reviewer(request, None, default="operator")
    await save_policy(policy, actor=actor, action="automation:resume")
    return {"policy": policy, "summary": describe(policy)}


@router.get("/next-slot")
async def next_slot(platform: str = Query(default="youtube"),
                    privacy: Optional[str] = Query(default=None)) -> dict[str, Any]:
    """The next configured publish window (Asia/Karachi) as a UTC timestamp —
    used by the scheduler worker so timezone logic lives in one place."""
    policy = await load_policy()
    limits = guardrails(policy)
    if platform not in ("youtube", "facebook", "instagram", "tiktok"):
        raise HTTPException(status_code=400, detail=f"unknown platform '{platform}'")
    if platform not in limits["auto_schedule_platforms"]:
        raise HTTPException(
            status_code=409,
            detail=f"platform '{platform}' is not in auto_schedule_platforms "
                   f"({', '.join(limits['auto_schedule_platforms'])})",
        )
    privacy = privacy or limits["auto_schedule_privacy"]
    if privacy not in ("private", "unlisted", "public"):
        raise HTTPException(status_code=422, detail="privacy must be private|unlisted|public")

    stored = await get_value(db.get(), "publish_windows")
    windows: list[str] = ["18:00"]
    if stored and isinstance(stored.get("value"), dict):
        try:
            windows = parse_publish_windows(stored["value"])
        except ValueError:
            windows = ["18:00"]
    return {
        "platform": platform,
        "privacy": privacy,
        "timezone": "Asia/Karachi",
        "publish_windows": windows,
        "local_time": default_publish_window(windows=windows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    pool = db.get()
    policy = await load_policy()
    limits = guardrails(policy)
    used = await _budget_used(pool)
    limit = int(limits["auto_publish_max_per_day"])

    queue = await pool.fetchrow(
        """
        SELECT
          (SELECT COUNT(*) FROM offers o
             WHERE o.state = 'evidence_needed'
               AND EXISTS (SELECT 1 FROM evidence e
                             WHERE e.offer_id = o.id AND e.official AND e.domain_ok))
            AS awaiting_verification,
          (SELECT COUNT(*) FROM offers o
             WHERE o.state IN ('verified', 'approved_for_video')
               AND NOT EXISTS (SELECT 1 FROM offer_scripts s WHERE s.offer_id = o.id))
            AS awaiting_script,
          (SELECT COUNT(*) FROM offers o
             WHERE o.state IN ('verified', 'approved_for_video')
               AND NOT EXISTS (SELECT 1 FROM renders r WHERE r.offer_id = o.id))
            AS awaiting_render,
          (SELECT COUNT(*) FROM offers WHERE state = 'verified')
            AS awaiting_offer_approval,
          (SELECT COUNT(*) FROM schedules WHERE state = 'needs_approval')
            AS awaiting_schedule_approval,
          (SELECT COUNT(*) FROM schedules WHERE state = 'scheduled')
            AS scheduled,
          (SELECT COUNT(*) FROM schedules WHERE state = 'failed')
            AS failed,
          (SELECT COUNT(*) FROM capture_sessions WHERE NOT redaction_reviewed)
            AS awaiting_redaction
        """
    )
    actions = await pool.fetch(
        """
        SELECT actor, action, entity, entity_id, detail::text AS detail, created_at
        FROM audit_log
        WHERE actor LIKE 'automation:%'
        ORDER BY created_at DESC
        LIMIT 20
        """
    )
    return {
        "policy": policy,
        "summary": describe(policy),
        "budget": {
            "used_today": used,
            "limit_per_day": limit,
            "remaining": max(0, limit - used),
            "exhausted": limit == 0 or used >= limit,
        },
        "queue": dict(queue or {}),
        "recent_automation_actions": [dict(row) for row in actions],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = ["router", "load_policy", "save_policy"]
