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
from preflight import VALID_MODES, build_preflight
from schedules_state import default_publish_window, parse_publish_windows
from settings_store import audit, get_language_policy, get_value, put_value

router = APIRouter(prefix="/automation", tags=["automation"])

PRESET_NAMES = ("manual", "assisted", "autopilot")


class PolicyIn(BaseModel):
    policy: dict[str, Any]


class PauseIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class StartIn(BaseModel):
    mode: str = "assisted"
    confirm_public: bool = False
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
    actor = effective_reviewer(request, None, default="operator", require=True)
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
    actor = effective_reviewer(request, None, default="operator", require=True)
    await save_policy(policy, actor=actor, action=f"automation:preset:{name}")
    return {"policy": policy, "summary": describe(policy)}


@router.post("/pause")
async def pause_automation(request: Request, body: Optional[PauseIn] = None) -> dict[str, Any]:
    """Global kill switch. Scheduled posts already approved are NOT cancelled;
    they are simply not auto-advanced. A human can still act."""
    policy = await load_policy()
    policy["paused"] = True
    actor = effective_reviewer(request, None, default="operator", require=True)
    await save_policy(policy, actor=actor, action="automation:pause",
                      detail={"note": (body.note if body else None)})
    return {"policy": policy, "summary": describe(policy)}


@router.post("/resume")
async def resume_automation(request: Request) -> dict[str, Any]:
    policy = await load_policy()
    policy["paused"] = False
    policy["dry_run"] = False
    actor = effective_reviewer(request, None, default="operator", require=True)
    await save_policy(policy, actor=actor, action="automation:resume")
    return {"policy": policy, "summary": describe(policy)}


@router.get("/preflight")
async def preflight(mode: str = Query(default="assisted")) -> dict[str, Any]:
    """Read-only readiness report for the dashboard Start card.

    The browser cannot start Docker; this endpoint only proves that the
    host-side launcher has the worker stack healthy and the gates are armed.
    """
    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown mode '{mode}' — known: {', '.join(sorted(VALID_MODES))}",
        )
    try:
        return await build_preflight(mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/start")
async def start_automation(body: StartIn, request: Request) -> dict[str, Any]:
    """Arm the selected safe preset after a fresh server-side preflight.

    This is deliberately not a Docker control: the host launcher starts the
    workers, and this endpoint refuses to arm if they are missing or stale.
    """
    if body.mode not in VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown mode '{body.mode}' — known: {', '.join(sorted(VALID_MODES))}",
        )
    if body.mode == "autopilot_public" and not body.confirm_public:
        raise HTTPException(
            status_code=422,
            detail="public autopilot requires confirm_public=true as an explicit acknowledgement",
        )

    report = await build_preflight(mode=body.mode)
    if not report["ready"]:
        names = "; ".join(c["label"] for c in report["blocking"])
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"preflight failed: {names}",
                "preflight": report,
            },
        )

    if body.mode == "assisted":
        policy = preset_policy("assisted")
        policy["guardrails"]["auto_schedule_privacy"] = "private"
    else:
        policy = preset_policy("autopilot")
        # Private is the default for a reason. Public is a separate, explicit
        # acknowledgement and starts with a one-post-per-day budget.
        policy["guardrails"]["auto_schedule_privacy"] = (
            "public" if body.mode == "autopilot_public" else "private"
        )
        if body.mode == "autopilot_public":
            policy["guardrails"]["auto_publish_max_per_day"] = 1

    policy["paused"] = False
    policy["dry_run"] = False
    policy = normalize_policy(policy)
    actor = effective_reviewer(request, None, default="operator", require=True)
    await save_policy(
        policy, actor=actor, action="automation:start",
        detail={
            "mode": body.mode,
            "note": body.note,
            "preflight_ready": True,
            "warning_count": len(report.get("warnings", [])),
        },
    )
    return {
        "started": True,
        "mode": body.mode,
        "policy": policy,
        "summary": describe(policy),
        "preflight": report,
    }


@router.post("/stop")
async def stop_automation(request: Request, body: Optional[PauseIn] = None) -> dict[str, Any]:
    """Explicit named stop, equivalent to the kill switch but audited as a
    stop so the operator's intent is unmistakable in the trail."""
    policy = await load_policy()
    policy["paused"] = True
    actor = effective_reviewer(request, None, default="operator", require=True)
    await save_policy(
        policy, actor=actor, action="automation:stop",
        detail={"note": (body.note if body else None)},
    )
    return {"started": False, "policy": policy, "summary": describe(policy)}


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


# ---------------------------------------------------------------- run-now (WP-D)

#: Stages run-now may ever touch. The human stages (verify/redaction review/
#: approve/schedule) are deliberately absent — no flag, no body field, no
#: "just this once": run-now ENQUEUES unattended work, it never performs a
#: human decision.
RUN_NOW_STAGES = ("collect", "scan", "script", "render")

_RUN_NOW_REARM = """
    ON CONFLICT (dedupe_key) DO UPDATE
    SET status = 'pending', run_after = now(), updated_at = now()
    WHERE jobs.status NOT IN ('leased', 'dead')
"""


@router.post("/run-now")
async def run_now(
    request: Request,
    stages: str = Query(
        default=",".join(RUN_NOW_STAGES),
        description="Comma-separated subset of: " + ", ".join(RUN_NOW_STAGES),
    ),
) -> dict:
    """"Run the pipeline now": make every unattended stage work its owed
    backlog DUE IMMEDIATELY (§ gap 15) — never the human gates.

    For each requested stage this (re)arms the durable owed-work records the
    workers already consume, so run-now is just "the worker sweep happens
    now": collect jobs for enabled sources, the trend-scan job, one script
    job per offer that earned a script, one render job per missing preset.
    Wedged (leased) and dead-lettered jobs are left alone — an operator
    resolves those explicitly, never by blind re-arm. Audited.
    """
    pool = db.get()
    requested = [s.strip() for s in stages.split(",") if s.strip()]
    unknown = [s for s in requested if s not in RUN_NOW_STAGES]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                "unknown stage(s): " + ", ".join(unknown) + " — run-now never "
                "touches human stages; allowed: " + ", ".join(RUN_NOW_STAGES)
            ),
        )
    armed: dict[str, int] = {}

    if "collect" in requested:
        armed["collect"] = await pool.fetchval(
            """
            WITH due AS (
                INSERT INTO jobs (kind, entity_id, payload, dedupe_key,
                                  max_attempts, run_after)
                SELECT 'collect', s.id, json_build_object('provider', s.provider,
                                                          'adapter', s.adapter),
                       'collect:' || s.id::text, 5, now()
                FROM sources s WHERE s.enabled
                ON CONFLICT (dedupe_key) DO UPDATE
                SET status = 'pending', run_after = now(), updated_at = now()
                WHERE jobs.status NOT IN ('leased', 'dead')
                RETURNING 1
            )
            SELECT COUNT(*) FROM due
            """,
        ) or 0

    if "scan" in requested:
        armed["scan"] = await pool.fetchval(
            """
            WITH due AS (
                INSERT INTO jobs (kind, payload, dedupe_key, max_attempts, run_after)
                VALUES ('trend_scan', '{}'::jsonb, 'trend_scan', 5, now())
                ON CONFLICT (dedupe_key) DO UPDATE
                SET status = 'pending', run_after = now(), updated_at = now()
                WHERE jobs.status NOT IN ('leased', 'dead')
                RETURNING 1
            )
            SELECT COUNT(*) FROM due
            """,
        ) or 0

    if "script" in requested:
        # Same "earned it" gate as the batch worker: verified (or already
        # approved) + official evidence on a matching domain + no script yet.
        armed["script"] = await pool.fetchval(
            """
            WITH due AS (
                INSERT INTO jobs (kind, entity_id, payload, dedupe_key,
                                  max_attempts, run_after)
                SELECT 'script', o.id,
                       json_build_object('offer_id', o.id::text),
                       'script:' || o.id::text, 5, now()
                FROM offers o
                WHERE o.state IN ('verified', 'approved_for_video')
                  AND (o.expires_at IS NULL OR o.expires_at > now())
                  AND EXISTS (
                      SELECT 1 FROM evidence e
                      WHERE e.offer_id = o.id AND e.official AND e.domain_ok)
                  AND NOT EXISTS (
                      SELECT 1 FROM offer_scripts s WHERE s.offer_id = o.id)
                ON CONFLICT (dedupe_key) DO UPDATE
                SET status = 'pending', run_after = now(), updated_at = now()
                WHERE jobs.status NOT IN ('leased', 'dead')
                RETURNING 1
            )
            SELECT COUNT(*) FROM due
            """,
        ) or 0

    if "render" in requested:
        # Same candidate contract as GET /render-candidates, boundary-free:
        # one job per (offer, language) whose latest script still misses a
        # QC-passed render. `sha256(convert_to(markdown,'UTF8'))` matches
        # script_version_hash used everywhere else (no content round-trip).
        narration = (await get_language_policy(pool))["narration_languages"]
        armed["render"] = await pool.fetchval(
            """
            WITH latest_script AS (
                SELECT DISTINCT ON (offer_id, language)
                       offer_id, language, version, markdown
                FROM offer_scripts ORDER BY offer_id, language, version DESC
            ),
            ready AS (
                SELECT o.id AS offer_id, ls.language, ls.version,
                       encode(sha256(convert_to(ls.markdown, 'UTF8')), 'hex')
                           AS script_hash,
                       (SELECT MAX(c.created_at) FROM capture_sessions c
                         WHERE c.offer_id = o.id AND c.redaction_reviewed)
                           AS reviewed_at
                FROM offers o
                JOIN latest_script ls ON ls.offer_id = o.id
                JOIN LATERAL (
                    SELECT 1 FROM capture_sessions c
                    WHERE c.offer_id = o.id AND c.redaction_reviewed
                    LIMIT 1
                ) rev ON TRUE
                WHERE o.state IN ('verified', 'approved_for_video')
                  AND ls.language = ANY($1::text[])
                  AND (SELECT COUNT(*) FROM renders r
                        WHERE r.offer_id = o.id AND r.language = ls.language
                          AND r.status = 'rendered' AND r.qc_status = 'passed'
                          AND r.script_version_hash =
                              encode(sha256(convert_to(ls.markdown, 'UTF8')), 'hex')) = 0
            ),
            due AS (
                INSERT INTO jobs (kind, entity_id, payload, dedupe_key,
                                  max_attempts, run_after)
                SELECT 'render_package', offer_id,
                       json_build_object('offer_id', offer_id::text,
                                         'language', language,
                                         'script_version', version),
                       'render:' || offer_id::text || ':' || language || ':'
                           || script_hash,
                       5, now()
                FROM ready
                ON CONFLICT (dedupe_key) DO UPDATE
                SET status = 'pending', run_after = now(), updated_at = now()
                WHERE jobs.status NOT IN ('leased', 'dead')
                RETURNING 1
            )
            SELECT COUNT(*) FROM due
            """,
            narration,
        ) or 0

    await audit(pool, actor=effective_reviewer(request, None, default="reviewer"),
                action="automation:run-now", entity="jobs", detail=armed)
    return {
        "stages": requested,
        "armed": armed,
        "total": sum(armed.values()),
        "note": ("owed unattended work armed now — verify/redaction review/"
                 "approve/schedule stay human"),
    }

