"""Preflight checks for the one-click “Start automation” action (v0.30).

The browser must never start Docker. This module only answers one question:
*if the host-side launcher has the worker stack running, is the system safe to
arm?* The dashboard calls it before showing Start; the start endpoint calls it
again server-side so a stale browser view cannot bypass a failing check.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from attention_api import build_attention
from automation import POLICY_KEY, PolicyError, default_policy, guardrails, normalize_policy
from settings_store import get_value, get_language_policy
from worker_health import snapshot as worker_snapshot

AUTOPILOT_MODES = {"autopilot_private", "autopilot_public"}
VALID_MODES = {"assisted", *AUTOPILOT_MODES}


def _check(check_id: str, label: str, status: str, detail: str,
           *, blocking: bool | None = None) -> dict[str, Any]:
    if blocking is None:
        blocking = status == "fail"
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
        "blocking": bool(blocking),
    }


async def load_policy(pool) -> dict[str, Any]:
    stored = await get_value(pool, POLICY_KEY)
    if not stored:
        return default_policy()
    try:
        return normalize_policy(stored["value"])
    except (PolicyError, ValueError):
        return default_policy()


def _storage_check() -> dict[str, Any]:
    backend = os.environ.get("MTK_STORAGE_BACKEND", "").strip().lower()
    if backend == "s3":
        required = {
            "MTK_S3_BUCKET": os.environ.get("MTK_S3_BUCKET", "").strip(),
            "MTK_S3_ENDPOINT": os.environ.get("MTK_S3_ENDPOINT", "").strip(),
            "MTK_S3_ACCESS_KEY": os.environ.get("MTK_S3_ACCESS_KEY", "").strip(),
            "MTK_S3_SECRET_KEY": os.environ.get("MTK_S3_SECRET_KEY", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            return _check(
                "storage", "Media storage", "fail",
                "S3 backend selected but missing " + ", ".join(missing) + ".",
            )
        return _check(
            "storage", "Media storage", "pass",
            f"S3-compatible object storage configured (bucket {required['MTK_S3_BUCKET']}).",
        )
    if backend in ("", "local"):
        root = (os.environ.get("MTK_STORAGE_LOCAL_ROOT", "").strip()
                or os.environ.get("MTK_MEDIA_ROOT", "").strip())
        if root and not os.path.isdir(root):
            return _check(
                "storage", "Media storage", "fail",
                f"Local media root {root!r} does not exist on the API host.",
            )
        detail = (
            f"Host-local media root {root}." if root
            else "Host-local media paths (single-host laptop mode)."
        )
        return _check("storage", "Media storage", "pass", detail)
    return _check(
        "storage", "Media storage", "warn",
        f"Unknown MTK_STORAGE_BACKEND={backend!r}; expected local or s3.",
    )


def _notifications_check(workers: dict[str, Any]) -> dict[str, Any]:
    monitor = next(
        (w for w in workers.get("workers", []) if w.get("name") == "monitor"), None,
    )
    metadata = (monitor or {}).get("metadata") or {}
    channels = metadata.get("notification_channels") or {}
    webhook = bool(channels.get("webhook"))
    email = bool(channels.get("email"))
    if webhook or email:
        names = [name for name, on in (("webhook", webhook), ("email", email)) if on]
        return _check(
            "notifications", "Alert delivery", "pass",
            "Configured: " + ", ".join(names) + ".",
        )
    return _check(
        "notifications", "Alert delivery", "warn",
        "No webhook or email channel is configured. The monitor will log alerts, "
        "but nobody will be paged while the dashboard is closed.",
    )


async def build_preflight(pool=None, mode: str = "assisted") -> dict[str, Any]:
    from db import get as get_pool
    pool = pool or get_pool()
    if mode not in VALID_MODES:
        raise ValueError(f"unknown mode {mode!r}")

    policy = await load_policy(pool)
    limits = guardrails(policy)
    workers = await worker_snapshot(pool)
    attention = await build_attention(pool)
    checks: list[dict[str, Any]] = []

    checks.append(_check(
        "api", "API and database", "pass",
        "The API is responding and the database is reachable.",
    ))

    if workers.get("all_online"):
        checks.append(_check(
            "workers", "Worker stack", "pass",
            f"{workers.get('online_count')}/{workers.get('expected_count')} expected workers online.",
        ))
    else:
        unhealthy = [
            w for w in workers.get("workers", [])
            if w.get("expected") and not w.get("online")
        ]
        names = ", ".join(f"{w['label']} ({w['state']})" for w in unhealthy[:7])
        checks.append(_check(
            "workers", "Worker stack", "fail",
            "Not healthy: " + (names or "unknown") + ". Run scripts/mtk-start.sh on the host.",
        ))

    render = next(
        (w for w in workers.get("workers", []) if w.get("name") == "render"), None,
    )
    render_meta = (render or {}).get("metadata") or {}
    ffmpeg = (render_meta.get("toolchain") or {}).get("ffmpeg") or render_meta.get("ffmpeg")
    if render and render.get("online") and ffmpeg:
        checks.append(_check(
            "render_toolchain", "Render toolchain", "pass",
            f"Render worker is online; FFmpeg at {ffmpeg}.",
        ))
    elif render and render.get("online"):
        checks.append(_check(
            "render_toolchain", "Render toolchain", "warn",
            "Render worker is online but did not report FFmpeg metadata.",
        ))
    else:
        checks.append(_check(
            "render_toolchain", "Render toolchain", "fail",
            "Render worker is not online, so no video can be rendered.",
        ))

    checks.append(_storage_check())

    notif = _notifications_check(workers)
    if mode in AUTOPILOT_MODES and notif["status"] != "pass":
        notif["status"] = "fail"
        notif["blocking"] = True
        notif["detail"] += " Unattended autopilot requires at least one delivery channel."
    checks.append(notif)

    account_rows = await pool.fetch(
        """
        SELECT platform, status, expires_at
        FROM platform_accounts
        ORDER BY updated_at DESC
        """
    )
    active = [r for r in account_rows if r["status"] == "active"
              and (r["expires_at"] is None
                   or r["expires_at"] > datetime.now(timezone.utc))]
    broken = [r for r in account_rows if r["status"] in ("token_expired", "revoked")]
    if active:
        detail = f"{len(active)} active platform account(s)."
        if broken:
            detail += f" {len(broken)} connection(s) need reconnecting."
        checks.append(_check(
            "accounts", "Publishing connections", "pass" if not broken else "warn", detail,
        ))
    else:
        checks.append(_check(
            "accounts", "Publishing connections", "fail",
            "No active platform account. Connect YouTube in Connections before starting.",
        ))

    stored_windows = await get_value(pool, "publish_windows")
    try:
        windows = (stored_windows or {}).get("value", {}).get("windows", [])
        windows = [w for w in windows if isinstance(w, str) and w]
    except AttributeError:
        windows = []
    if windows:
        checks.append(_check(
            "publish_windows", "Publish windows", "pass",
            "Configured: " + ", ".join(windows) + " (Asia/Karachi).",
        ))
    else:
        checks.append(_check(
            "publish_windows", "Publish windows", "warn",
            "No publish windows saved; the scheduler will use 18:00 Asia/Karachi.",
        ))

    limit = int(limits["auto_publish_max_per_day"])
    used = int(attention.get("budget", {}).get("used_today", 0))
    if mode in AUTOPILOT_MODES and limit <= 0:
        checks.append(_check(
            "budget", "Automation budget", "fail",
            "Autopilot needs a positive daily auto-publish limit.",
        ))
    elif mode in AUTOPILOT_MODES and used >= limit:
        checks.append(_check(
            "budget", "Automation budget", "warn",
            f"Daily budget already used ({used}/{limit}); publishing resumes tomorrow.",
        ))
    else:
        checks.append(_check(
            "budget", "Automation budget", "pass",
            f"{used}/{limit} auto-approved posts used today.",
        ))

    language = await get_language_policy(pool)
    checks.append(_check(
        "language", "Language policy", "pass",
        "English package; Urdu voiceover "
        + ("enabled." if language.get("urdu_voiceover_enabled") else "opt-in and currently off."),
    ))

    if attention.get("total"):
        checks.append(_check(
            "attention", "Needs You inbox", "warn",
            f"{attention['total']} item(s) are waiting. Starting does not bypass them.",
        ))
    else:
        checks.append(_check(
            "attention", "Needs You inbox", "pass",
            "No pending human actions.",
        ))

    blocking = [c for c in checks if c["blocking"]]
    warnings = [c for c in checks if c["status"] == "warn"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "ready": not blocking,
        "blocking": blocking,
        "warnings": warnings,
        "checks": checks,
        "worker_status": workers,
        "attention": {
            "total": attention.get("total", 0),
            "counts": attention.get("counts", {}),
            "severity": attention.get("severity", "ok"),
        },
        "policy": {
            "mode": policy.get("mode"),
            "paused": policy.get("paused"),
            "dry_run": policy.get("dry_run"),
            "stages": policy.get("stages"),
        },
    }


__all__ = ["AUTOPILOT_MODES", "VALID_MODES", "build_preflight", "load_policy"]
