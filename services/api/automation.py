"""Automation policy — settings-driven human control vs. automation.

The platform has always had hard-coded human gates. This module makes the
*policy* explicit, validated, and shared by every gate:

  - manual     : every meaningful step waits for a person. Nothing advances.
  - assisted   : collection / verification / scripting / rendering are
                 automatic; approval and scheduling stay human.
  - autopilot  : every stage may advance automatically, but only inside the
                 guardrails below and with every action audited as
                 ``automation:<stage>``.

Non-negotiable safety rules are NOT configurable:

  * evidence must be official and provider-domain checked (state.py gate),
  * redaction review of footage is always a human attestation,
  * the exact script hash approved must equal the render's hash,
  * the daily auto-publish budget is enforced server-side.

The policy is stored under settings key ``automation_policy``. Workers read
``GET /automation/policy``; the API re-checks the policy on every gated write,
so a forged worker call cannot bypass a ``human`` stage.
"""

from __future__ import annotations

import copy
from typing import Any, Final, Optional

POLICY_KEY: Final = "automation_policy"
POLICY_SCHEMA_VERSION: Final = 1

PLATFORMS: Final = ("youtube", "facebook", "instagram", "tiktok")
PRIVACY: Final = ("private", "unlisted", "public")

STAGES: Final = (
    "collect",     # poll sources and ingest candidates
    "verify",      # evidence + extraction -> verified
    "script",      # deterministic claim script
    "render",      # FFmpeg exports from reviewed captures
    "approve",     # verified -> approved_for_video, schedule approval
    "schedule",    # create queue entries at the next publish window
)

STAGE_MODES: Final = ("human", "auto")
MODES: Final = ("manual", "assisted", "autopilot", "custom")

# Human-readable stage descriptions used by the dashboard/API.
STAGE_LABELS: Final = {
    "collect": "Collect candidates from registered sources",
    "verify": "Collect official evidence and promote to verified",
    "script": "Generate the versioned claim script",
    "render": "Render captions / 16:9 / 9:16 exports",
    "approve": "Approve the offer for video and approve each post",
    "schedule": "Queue approved posts at a publish window",
}

# Guarantees that can never be switched off (documented + surfaced in the UI).
FIXED_GUARANTEES: Final = (
    "Official, provider-domain-checked evidence is required before 'verified'.",
    "Redaction review of capture footage is always a human attestation.",
    "A render may only publish when its script hash equals the approved hash.",
    "Every automation action is audited as automation:<stage>.",
    "An offer expiry / correction auto-pauses its scheduled posts.",
)

_DEFAULT_GUARDRAILS: Final[dict[str, Any]] = {
    "auto_verify_min_confidence": 0.0,
    "auto_verify_max_evidence_age_hours": 72,
    "auto_approve_requires_render": True,
    "auto_approve_block_unsafe_commands": True,
    "auto_schedule_platforms": ["youtube"],
    "auto_schedule_privacy": "private",
    "auto_publish_max_per_day": 3,
    "auto_retry": True,
    "retry_max_attempts": 3,
    "retry_base_seconds": 300,
    # WP-F (§5.5): hard money caps, checked by the workers BEFORE spending.
    # Exhausted → the stage degrades (rules-only extraction / capture audio)
    # and shows in Needs-You — never a surprise bill.
    "max_llm_cost_per_day_usd": 0.5,
    "max_tts_chars_per_day": 50_000,
    # EP-03 G18: automation may only auto-shortlist so many topics for research
    # per day (low-risk explainers). A human promote is never capped.
    "auto_research_max_per_day": 2,
}

_STAGE_PRESETS: Final[dict[str, dict[str, str]]] = {
    "manual": {stage: "human" for stage in STAGES},
    "assisted": {
        "collect": "auto",
        "verify": "auto",
        "script": "auto",
        "render": "auto",
        "approve": "human",
        "schedule": "human",
    },
    "autopilot": {stage: "auto" for stage in STAGES},
}

_PRESET_GUARDRAILS: Final[dict[str, dict[str, Any]]] = {
    "manual": {"auto_retry": False, "auto_publish_max_per_day": 0,
               "max_llm_cost_per_day_usd": 0, "max_tts_chars_per_day": 0},
    "assisted": {},
    "autopilot": {"auto_publish_max_per_day": 2, "auto_schedule_privacy": "private"},
}


class PolicyError(ValueError):
    """The submitted policy is invalid (surface as HTTP 422)."""


class AutomationDenied(PermissionError):
    """Automation is not permitted for this stage (surface as HTTP 403/429)."""


# ------------------------------------------------------------------ defaults


def default_policy() -> dict[str, Any]:
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "mode": "assisted",
        "paused": False,
        "dry_run": False,
        "stages": dict(_STAGE_PRESETS["assisted"]),
        "guardrails": copy.deepcopy(_DEFAULT_GUARDRAILS),
    }


def preset_policy(name: str) -> dict[str, Any]:
    """A complete, normalized preset policy. Unknown names raise PolicyError."""
    if name not in _STAGE_PRESETS:
        raise PolicyError(f"unknown preset '{name}' — known: {', '.join(_STAGE_PRESETS)}")
    guardrails = copy.deepcopy(_DEFAULT_GUARDRAILS)
    guardrails.update(copy.deepcopy(_PRESET_GUARDRAILS.get(name, {})))
    return normalize_policy({
        "mode": name,
        "paused": False,
        "dry_run": False,
        "stages": dict(_STAGE_PRESETS[name]),
        "guardrails": guardrails,
    })


def list_presets() -> dict[str, dict[str, Any]]:
    return {name: preset_policy(name) for name in _STAGE_PRESETS}


# ---------------------------------------------------------------- validation


def _as_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise PolicyError(f"{field} must be true or false")


def _as_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolicyError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise PolicyError(f"{field} must be between {minimum} and {maximum}")
    return value


def _as_float(value: Any, field: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"{field} must be a number")
    number = float(value)
    if not minimum <= number <= maximum:
        raise PolicyError(f"{field} must be between {minimum} and {maximum}")
    return number


def _normalize_guardrails(raw: Any, base: dict[str, Any]) -> dict[str, Any]:
    if raw is None:
        return copy.deepcopy(base)
    if not isinstance(raw, dict):
        raise PolicyError("guardrails must be an object")
    unknown = set(raw) - set(_DEFAULT_GUARDRAILS)
    if unknown:
        raise PolicyError(f"unknown guardrail(s): {', '.join(sorted(unknown))}")

    out = copy.deepcopy(base)
    for key, value in raw.items():
        if key == "auto_verify_min_confidence":
            out[key] = _as_float(value, key, minimum=0.0, maximum=1.0)
        elif key == "auto_verify_max_evidence_age_hours":
            out[key] = _as_int(value, key, minimum=1, maximum=720)
        elif key in ("auto_approve_requires_render", "auto_approve_block_unsafe_commands",
                     "auto_retry"):
            out[key] = _as_bool(value, key)
        elif key == "auto_schedule_platforms":
            if not isinstance(value, list) or not value:
                raise PolicyError("auto_schedule_platforms must be a non-empty list")
            platforms: list[str] = []
            for platform in value:
                if platform not in PLATFORMS:
                    raise PolicyError(
                        f"unknown platform '{platform}' — known: {', '.join(PLATFORMS)}")
                if platform not in platforms:
                    platforms.append(platform)
            out[key] = platforms
        elif key == "auto_schedule_privacy":
            if value not in PRIVACY:
                raise PolicyError(
                    f"auto_schedule_privacy must be one of: {', '.join(PRIVACY)}")
            out[key] = value
        elif key == "auto_publish_max_per_day":
            out[key] = _as_int(value, key, minimum=0, maximum=100)
        elif key == "auto_research_max_per_day":
            out[key] = _as_int(value, key, minimum=0, maximum=100)
        elif key == "retry_max_attempts":
            out[key] = _as_int(value, key, minimum=0, maximum=10)
        elif key == "retry_base_seconds":
            out[key] = _as_int(value, key, minimum=30, maximum=86_400)
        elif key == "max_llm_cost_per_day_usd":
            out[key] = _as_float(value, key, minimum=0.0, maximum=1_000.0)
        elif key == "max_tts_chars_per_day":
            out[key] = _as_int(value, key, minimum=0, maximum=5_000_000)
    return out


def _normalize_stages(raw: Any, base: dict[str, str]) -> dict[str, str]:
    if raw is None:
        return dict(base)
    if not isinstance(raw, dict):
        raise PolicyError("stages must be an object")
    unknown = set(raw) - set(STAGES)
    if unknown:
        raise PolicyError(f"unknown stage(s): {', '.join(sorted(unknown))}")
    out = dict(base)
    for stage, mode in raw.items():
        if mode not in STAGE_MODES:
            raise PolicyError(
                f"stage '{stage}' must be one of: {', '.join(STAGE_MODES)}")
        out[stage] = mode
    return out


_TOP_LEVEL: Final = {"schema_version", "mode", "paused", "dry_run", "stages", "guardrails"}


def normalize_policy(raw: Any, *, base: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Validate + fill a policy payload.

    Partial updates are supported: omitted stages/guardrails keep their current
    value. Sending ``mode`` without ``stages`` selects that preset's stages.
    The resulting ``mode`` is the preset name only when the stages still match
    that preset; otherwise it is ``custom``.
    """
    if not isinstance(raw, dict):
        raise PolicyError("automation policy must be an object")
    unknown = set(raw) - _TOP_LEVEL
    if unknown:
        raise PolicyError(f"unknown policy field(s): {', '.join(sorted(unknown))}")

    source = copy.deepcopy(base) if base is not None else default_policy()
    mode = raw.get("mode", source.get("mode", "assisted"))
    if mode not in MODES:
        raise PolicyError(f"mode must be one of: {', '.join(MODES)}")

    # Choosing a preset explicitly replaces its stages (and, when the caller
    # supplies nothing else, its guardrail defaults). A partial update that
    # does not name a preset must preserve every unspecified stage — otherwise
    # toggling one control would silently reset the rest to `assisted`.
    explicit_mode = "mode" in raw
    if explicit_mode and mode in _STAGE_PRESETS:
        stages_source = _STAGE_PRESETS[mode]
    else:
        stages_source = source.get("stages", _STAGE_PRESETS["assisted"])

    stages = _normalize_stages(raw.get("stages"), stages_source)

    guardrail_base = copy.deepcopy(source.get("guardrails", _DEFAULT_GUARDRAILS))
    if (explicit_mode and mode in _STAGE_PRESETS
            and "guardrails" not in raw and "stages" not in raw):
        guardrail_base = copy.deepcopy(_DEFAULT_GUARDRAILS)
        guardrail_base.update(copy.deepcopy(_PRESET_GUARDRAILS.get(mode, {})))
    guardrails = _normalize_guardrails(raw.get("guardrails"), guardrail_base)

    # mode is derived: a preset name only if the stages are exactly that preset.
    matched = next(
        (name for name, preset_stages in _STAGE_PRESETS.items() if preset_stages == stages),
        "custom",
    )

    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "mode": matched,
        "paused": _as_bool(raw.get("paused", source.get("paused", False)), "paused"),
        "dry_run": _as_bool(raw.get("dry_run", source.get("dry_run", False)), "dry_run"),
        "stages": stages,
        "guardrails": guardrails,
    }


# ------------------------------------------------------------------ queries


def stage_mode(policy: dict[str, Any], stage: str) -> str:
    if stage not in STAGES:
        raise PolicyError(f"unknown stage '{stage}'")
    return (policy.get("stages") or {}).get(stage, "human")


def can_automate(policy: dict[str, Any], stage: str) -> bool:
    return (
        not policy.get("paused", False)
        and not policy.get("dry_run", False)
        and stage_mode(policy, stage) == "auto"
    )


def guardrails(policy: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return (policy or default_policy()).get("guardrails", _DEFAULT_GUARDRAILS)


AUTOMATION_PREFIX: Final = "automation:"


def is_automation_actor(actor: Optional[str]) -> bool:
    return bool(actor and actor.strip().lower().startswith(AUTOMATION_PREFIX))


def actor_stage(actor: Optional[str]) -> Optional[str]:
    if not is_automation_actor(actor):
        return None
    return (actor or "").strip().split(":", 1)[1].strip().lower() or None


def authorize(policy: dict[str, Any], stage: str, actor: Optional[str]) -> str:
    """Raise AutomationDenied unless ``actor`` may automate ``stage`` now.

    Returns the canonical actor string to record in the audit trail.
    """
    if not is_automation_actor(actor):
        raise AutomationDenied("this action requires a named human reviewer")
    if stage not in STAGES:
        raise PolicyError(f"unknown stage '{stage}'")
    claimed = actor_stage(actor)
    if claimed != stage:
        raise AutomationDenied(
            f"automation identity '{actor}' cannot act on stage '{stage}'")
    if policy.get("paused", False):
        raise AutomationDenied(
            "automation is paused by the operator — a human must resume it in Settings")
    if policy.get("dry_run", False):
        raise AutomationDenied(
            "automation is in dry-run mode — no state changes are allowed")
    if stage_mode(policy, stage) != "auto":
        raise AutomationDenied(
            f"stage '{stage}' is set to human control in Settings — "
            "a named reviewer must perform this action")
    return f"{AUTOMATION_PREFIX}{stage}"


def describe(policy: dict[str, Any]) -> dict[str, Any]:
    """Compact, dashboard-friendly summary of an effective policy."""
    controls = [
        {
            "stage": stage,
            "label": STAGE_LABELS[stage],
            "mode": stage_mode(policy, stage),
            "active": can_automate(policy, stage),
        }
        for stage in STAGES
    ]
    active_stages = [c["stage"] for c in controls if c["active"]]
    human_stages = [c["stage"] for c in controls if not c["active"]]
    if policy.get("paused", False):
        state = "paused"
    elif policy.get("dry_run", False):
        state = "dry_run"
    else:
        state = "running" if active_stages else "manual"
    return {
        "state": state,
        "mode": policy.get("mode", "custom"),
        "paused": bool(policy.get("paused", False)),
        "dry_run": bool(policy.get("dry_run", False)),
        "controls": controls,
        "automation_stages": active_stages,
        "human_stages": human_stages,
        "guardrails": guardrails(policy),
        "fixed_guarantees": list(FIXED_GUARANTEES),
    }
