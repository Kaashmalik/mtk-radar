"""The operator's “Needs You” inbox (v0.30).

Every automation gate that requires a human lands here with a deep link. The
endpoint is intentionally read-only: approving, re-rendering and reconnecting
still go through their existing audited routes.

The monitor also reads this endpoint and turns counts into alerts, so a
pending approval cannot sit silently for days while the dashboard is closed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter

import db
from automation import PolicyError, default_policy, normalize_policy, guardrails, POLICY_KEY
from settings_store import get_value
from worker_health import attention_items as worker_attention_items
from worker_health import snapshot as worker_snapshot

router = APIRouter(prefix="/attention", tags=["attention"])

LIMIT_PER_KIND = 50
_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _json(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except ValueError:
            return {}
    return {}


async def _load_policy(pool) -> dict[str, Any]:
    stored = await get_value(pool, POLICY_KEY)
    if not stored:
        return default_policy()
    try:
        return normalize_policy(stored["value"])
    except (PolicyError, ValueError):
        return default_policy()


async def _budget_used(pool) -> int:
    return int(await pool.fetchval(
        """
        SELECT COUNT(*) FROM schedules
        WHERE approved_by LIKE 'automation:%'
          AND updated_at >= date_trunc('day', now())
        """
    ) or 0)


def _row_total(rows: list[Any], fallback: int = 0) -> int:
    if not rows:
        return fallback
    try:
        return int(rows[0]["total_count"])
    except (KeyError, TypeError, ValueError):
        return len(rows)


def _item(*, kind: str, entity_id: Any, severity: str, title: str,
          detail: str, href: str, action: str, at: Any = None,
          **extra: Any) -> dict[str, Any]:
    item = {
        "id": f"{kind}:{entity_id}",
        "kind": kind,
        "severity": severity,
        "title": title,
        "detail": detail,
        "href": href,
        "action": action,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "at": _iso(at),
    }
    item.update(extra)
    return item


async def build_attention(pool=None) -> dict[str, Any]:
    pool = pool or db.get()
    policy = await _load_policy(pool)
    limits = guardrails(policy)
    paused = bool(policy.get("paused"))
    stages = policy.get("stages", {})
    items: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    by_kind: dict[str, dict[str, Any]] = {}

    def add(kind: str, count: int, items_for_kind: list[dict[str, Any]]) -> None:
        counts[kind] = count
        items.extend(items_for_kind)
        by_kind[kind] = {
            "count": count,
            "severity": min(
                (i["severity"] for i in items_for_kind),
                key=lambda s: _SEVERITY_RANK.get(s, 9),
                default="info",
            ),
            "href": items_for_kind[0]["href"] if items_for_kind else "/attention",
            "label": {
                "redaction": "Redaction reviews",
                "offer_approval": "Offers ready to approve",
                "schedule_approval": "Posts waiting for approval",
                "render_failed": "Render / QC failures",
                "publish_failed": "Publishing failures / holds",
                "correction": "Corrections to resolve",
                "offer_expiry": "Expiring / recheck offers",
                "token": "Platform connections",
                "verification": "Evidence waiting for verification",
                "budget": "Automation budget",
                "worker": "Worker health",
                "job": "Stuck / dead jobs",
            }.get(kind, kind.replace("_", " ").title()),
        }

    # ---- redaction review: always a human attestation (§4) ----------------
    rows = await pool.fetch(
        """
        SELECT c.id, c.offer_id, o.title, o.provider, c.created_at,
               COUNT(*) OVER() AS total_count
        FROM capture_sessions c JOIN offers o ON o.id = c.offer_id
        WHERE NOT c.redaction_reviewed
        ORDER BY c.created_at ASC
        LIMIT $1
        """,
        LIMIT_PER_KIND,
    )
    add("redaction", _row_total(rows), [
        _item(
            kind="redaction", entity_id=r["id"], severity="warning",
            title=f"Review redaction: {r['title']}",
            detail=("The capture is recorded but the redaction attestation is "
                    "missing. Publishing is blocked until a human reviews it."),
            href=f"/offers/{r['offer_id']}", action="Review capture",
            at=r["created_at"], offer_id=str(r["offer_id"]),
        )
        for r in rows
    ])

    # ---- offers with a passed render waiting for approval -----------------
    if stages.get("approve") != "auto" or paused:
        rows = await pool.fetch(
            """
            SELECT o.id, o.title, o.provider, o.state::text AS state, o.updated_at,
                   COUNT(*) OVER() AS total_count
            FROM offers o
            WHERE o.state = 'verified'
              AND EXISTS (SELECT 1 FROM offer_scripts s WHERE s.offer_id = o.id)
              AND EXISTS (
                SELECT 1 FROM renders r
                WHERE r.offer_id = o.id
                  AND r.status = 'rendered' AND r.qc_status = 'passed'
              )
            ORDER BY o.updated_at ASC
            LIMIT $1
            """,
            LIMIT_PER_KIND,
        )
        add("offer_approval", _row_total(rows), [
            _item(
                kind="offer_approval", entity_id=r["id"], severity="warning",
                title=f"Approve offer: {r['title']}",
                detail=("A QC-passed render is ready. Approval pins the exact script "
                        "version and is recorded in the audit trail."),
                href=f"/offers/{r['id']}", action="Review offer",
                at=r["updated_at"], provider=r["provider"],
            )
            for r in rows
        ])
    else:
        add("offer_approval", 0, [])

    # ---- schedule approvals ----------------------------------------------
    rows = await pool.fetch(
        """
        SELECT s.id, s.offer_id, o.title, s.platform, s.local_time, s.updated_at,
               COUNT(*) OVER() AS total_count
        FROM schedules s JOIN offers o ON o.id = s.offer_id
        WHERE s.state = 'needs_approval'
        ORDER BY s.local_time ASC
        LIMIT $1
        """,
        LIMIT_PER_KIND,
    )
    add("schedule_approval", _row_total(rows), [
        _item(
            kind="schedule_approval", entity_id=r["id"], severity="warning",
            title=f"Approve {r['platform']} post: {r['title']}",
            detail=f"Scheduled window: {_iso(r['local_time'])}.",
            href="/calendar", action="Approve post",
            at=r["updated_at"], offer_id=str(r["offer_id"]),
        )
        for r in rows
    ])

    # ---- render / QC dead letters ---------------------------------------
    rows = await pool.fetch(
        """
        SELECT r.id, r.offer_id, o.title, r.preset, r.status, r.qc_status,
               r.created_at, COUNT(*) OVER() AS total_count
        FROM renders r JOIN offers o ON o.id = r.offer_id
        WHERE r.status IN ('render_failed', 'qc_failed')
           OR r.qc_status = 'failed'
           OR (r.status = 'rendered' AND r.qc_status = 'not_checked')
        ORDER BY r.created_at DESC
        LIMIT $1
        """,
        LIMIT_PER_KIND,
    )
    add("render_failed", _row_total(rows), [
        _item(
            kind="render_failed", entity_id=r["id"], severity="error",
            title=f"Render failed: {r['title']}",
            detail=(f"{r['preset']} output is {r['status']} "
                    f"(QC: {r['qc_status']}). A failed attempt can never publish."),
            href="/queue", action="Open queue",
            at=r["created_at"], offer_id=str(r["offer_id"]),
        )
        for r in rows
    ])

    # ---- publishing failures and freshness holds -------------------------
    rows = await pool.fetch(
        """
        SELECT s.id, s.offer_id, o.title, s.platform, s.state::text AS state,
               s.retry_count, s.outcome_detail::text AS outcome_detail,
               s.updated_at, COUNT(*) OVER() AS total_count
        FROM schedules s JOIN offers o ON o.id = s.offer_id
        WHERE s.state = 'failed'
           OR (s.state = 'paused' AND s.outcome_detail @> '{"hold": true}'::jsonb)
        ORDER BY s.updated_at DESC
        LIMIT $1
        """,
        LIMIT_PER_KIND,
    )
    publish_items: list[dict[str, Any]] = []
    for r in rows:
        outcome = _json(r.get("outcome_detail"))
        reason = outcome.get("error") or outcome.get("hold_reason") or outcome.get("reason")
        publish_items.append(_item(
            kind="publish_failed", entity_id=r["id"], severity="error",
            title=f"Publishing {r['state']}: {r['title']}",
            detail=(f"{r['platform']} after {r['retry_count']} retries"
                    + (f": {reason}" if reason else ".")),
            href="/calendar", action="Inspect post",
            at=r["updated_at"], offer_id=str(r["offer_id"]),
            platform=r["platform"],
        ))
    add("publish_failed", _row_total(rows), publish_items)

    # ---- corrections -----------------------------------------------------
    rows = await pool.fetch(
        """
        SELECT o.id, o.title, o.provider, o.correction_note, o.updated_at,
               COUNT(*) OVER() AS total_count
        FROM offers o
        WHERE o.state = 'corrected'
        ORDER BY o.updated_at DESC
        LIMIT $1
        """,
        LIMIT_PER_KIND,
    )
    add("correction", _row_total(rows), [
        _item(
            kind="correction", entity_id=r["id"], severity="warning",
            title=f"Resolve correction: {r['title']}",
            detail=(r["correction_note"] or
                    "The offer changed; affected posts are paused until the correction is reviewed."),
            href=f"/offers/{r['id']}", action="Resolve correction",
            at=r["updated_at"], provider=r["provider"],
        )
        for r in rows
    ])

    # ---- expiry / recheck deadline --------------------------------------
    rows = await pool.fetch(
        """
        SELECT o.id, o.title, o.provider, o.state::text AS state,
               o.expires_at, o.recheck_at, o.updated_at,
               COUNT(*) OVER() AS total_count
        FROM offers o
        WHERE o.state IN ('verified', 'approved_for_video', 'published')
          AND ((o.expires_at IS NOT NULL AND o.expires_at <= now())
               OR o.recheck_at <= now())
        ORDER BY o.recheck_at ASC
        LIMIT $1
        """,
        LIMIT_PER_KIND,
    )
    add("offer_expiry", _row_total(rows), [
        _item(
            kind="offer_expiry", entity_id=r["id"], severity="error",
            title=f"Expired or needs recheck: {r['title']}",
            detail=(f"State {r['state']}; expires {_iso(r['expires_at']) or 'n/a'}, "
                    f"recheck due {_iso(r['recheck_at']) or 'n/a'}. Affected posts are paused."),
            href=f"/offers/{r['id']}", action="Recheck offer",
            at=r["updated_at"], provider=r["provider"],
        )
        for r in rows
    ])

    # ---- platform credentials -------------------------------------------
    rows = await pool.fetch(
        """
        SELECT a.id, a.platform, a.account_handle, a.status, a.expires_at,
               a.last_error, a.updated_at, COUNT(*) OVER() AS total_count
        FROM platform_accounts a
        WHERE a.status IN ('token_expired', 'revoked')
           OR (a.status = 'active' AND a.expires_at IS NOT NULL
               AND a.expires_at <= now() + interval '3 days')
        ORDER BY a.updated_at DESC
        LIMIT $1
        """,
        LIMIT_PER_KIND,
    )
    add("token", _row_total(rows), [
        _item(
            kind="token", entity_id=r["id"], severity="error",
            title=f"Reconnect {r['platform']}: {r['account_handle']}",
            detail=(r["last_error"] or
                    f"Credential status is {r['status']}; publishing is paused for this account."),
            href="/connections", action="Reconnect account",
            at=r["updated_at"], platform=r["platform"],
        )
        for r in rows
    ])

    # ---- verification desk (only when a human must decide) ---------------
    if stages.get("verify") != "auto" or paused:
        rows = await pool.fetch(
            """
            SELECT o.id, o.title, o.provider, o.updated_at,
                   COUNT(*) OVER() AS total_count
            FROM offers o
            WHERE o.state = 'evidence_needed'
              AND EXISTS (
                SELECT 1 FROM evidence e
                WHERE e.offer_id = o.id AND e.official AND e.domain_ok
              )
            ORDER BY o.updated_at ASC
            LIMIT $1
            """,
            LIMIT_PER_KIND,
        )
        add("verification", _row_total(rows), [
            _item(
                kind="verification", entity_id=r["id"], severity="warning",
                title=f"Verify evidence: {r['title']}",
                detail="Official evidence exists; the verification stage is set to human.",
                href="/queue", action="Verify evidence",
                at=r["updated_at"], provider=r["provider"],
            )
            for r in rows
        ])
    else:
        add("verification", 0, [])

    # ---- daily automation budget ----------------------------------------
    used = await _budget_used(pool)
    limit = int(limits["auto_publish_max_per_day"])
    exhausted = limit == 0 or used >= limit
    if policy.get("mode") == "autopilot" and exhausted:
        add("budget", 1, [_item(
            kind="budget", entity_id="daily", severity="warning",
            title="Automation budget exhausted",
            detail=(f"{used}/{limit} auto-approved posts today. "
                    "Unattended publishing pauses until tomorrow or a budget change."),
            href="/settings", action="Adjust budget",
            at=datetime.now(timezone.utc),
        )])
    else:
        add("budget", 0, [])

    # ---- worker liveness -------------------------------------------------
    workers = await worker_snapshot(pool)
    worker_items = worker_attention_items(workers)
    add("worker", len(worker_items), worker_items)

    # ---- durable jobs (§8.A): wedged work must surface, never go quiet ----
    job_items: list[dict[str, Any]] = []
    expired = await pool.fetch(
        """
        SELECT id, kind, lease_holder, lease_expires_at, attempts
        FROM jobs WHERE status = 'leased' AND lease_expires_at <= now()
        ORDER BY lease_expires_at ASC LIMIT 20
        """,
    )
    for row in expired:
        job_items.append(_item(
            kind="job", entity_id=row["id"], severity="error",
            title=f"{row['kind']} job lease expired without an outcome",
            detail=f"holder={row['lease_holder']} attempts={row['attempts']} — "
                   "a human must check the effects before this work is retried",
            at=row["lease_expires_at"],
        ))
    dead = await pool.fetch(
        """
        SELECT id, kind, attempts, max_attempts, last_error, updated_at
        FROM jobs WHERE status = 'dead'
        ORDER BY updated_at DESC LIMIT 20
        """,
    )
    for row in dead:
        job_items.append(_item(
            kind="job", entity_id=row["id"], severity="warning",
            title=f"{row['kind']} job dead-lettered after {row['attempts']} attempt(s)",
            detail=row["last_error"] or "no error detail recorded",
            at=row["updated_at"],
        ))
    add("job", len(job_items), job_items)

    # Stable presentation: errors first, then warnings, newest first inside
    # each severity band.
    grouped: list[dict[str, Any]] = []
    for severity in ("error", "warning", "info"):
        bucket = [i for i in items if i["severity"] == severity]
        bucket.sort(key=lambda i: str(i.get("at") or ""), reverse=True)
        grouped.extend(bucket)
    items = grouped

    total = sum(counts.values())
    if any(i["severity"] == "error" for i in items):
        severity = "error"
    elif any(i["severity"] == "warning" for i in items):
        severity = "warning"
    else:
        severity = "ok"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "human_total": total,
        "severity": severity,
        "counts": counts,
        "by_kind": by_kind,
        "items": items,
        "workers": workers,
        "budget": {
            "used_today": used,
            "limit_per_day": limit,
            "remaining": max(0, limit - used),
            "exhausted": exhausted,
        },
        "policy": {
            "mode": policy.get("mode"),
            "paused": paused,
            "stages": stages,
        },
    }


@router.get("")
async def get_attention() -> dict[str, Any]:
    return await build_attention()


__all__ = ["build_attention", "router"]
