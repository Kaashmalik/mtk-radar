"""Claim script & checklist generator (master plan §4, weeks 5-6/§18 weeks 7-8).

Turns a VERIFIED offer into:
- a claim checklist (ordered, human-checked steps),
- command cards (only from approved sources; destructive/billable flagged;
  required expected output documented),
- script.md following the claim-video sequence table (§15): hook + checked-on
  date, eligibility up front, real-time claim, verification of the benefit,
  wrap-up summary card with renewal warning and source links.

HARD RULE: generation is blocked unless the offer state allows video
(can_generate_video) — unverified offers can never enter script generation.
Every factual statement cites its evidence URL.
"""

from datetime import datetime
from typing import Any, Final

from jsonb import decode_list, decode_mapping

VIDEO_STATES: Final = frozenset({"verified", "approved_for_video", "published"})


class ScriptGateError(PermissionError):
    """Raised when script generation is attempted for an unverified offer."""


def _fmt_date(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y")
    return str(value)


def assert_video_allowed(state: str) -> None:
    if state not in VIDEO_STATES:
        raise ScriptGateError(
            f"script generation blocked: offer state is '{state}' — verified "
            "with official evidence is required (master plan §3)"
        )


def build_checklist(offer: dict) -> list[dict]:
    """Ordered pre-flight + claim steps the operator physically checks off."""
    eligibility = decode_mapping(offer.get("eligibility"))
    steps: list[dict] = [
        {"order": 0, "kind": "manual_check", "text": "Recheck offer freshness: official terms page unchanged, not expired (recheck_at)." },
        {"order": 1, "kind": "manual_check", "text": "Confirm operator eligibility on own account before recording (no staged successes)."},
    ]
    if eligibility.get("countries"):
        steps.append({
            "order": len(steps),
            "kind": "manual_check",
            "text": f"Confirm country eligibility: {', '.join(eligibility['countries'])}.",
        })
    if eligibility.get("studentStatus") or eligibility.get("verificationRequired"):
        steps.append({
            "order": len(steps),
            "kind": "manual_check",
            "text": "Verification document/proof ready (enrollment or startup status).",
        })

    for claim_step in decode_list(offer.get("claim_steps")):
        step = dict(claim_step)
        step["order"] = len(steps)  # sequential; never trust caller-provided order
        steps.append(step)

    steps.append({
        "order": len(steps),
        "kind": "manual_check",
        "text": "Show where the benefit appears in the provider account (verification checkpoint).",
    })
    steps.append({
        "order": len(steps),
        "kind": "manual_check",
        "text": "Redaction review passed: no secrets in footage, terminal, or transcript (§11).",
    })
    return steps


def build_command_cards(claim_steps: list[dict]) -> list[dict]:
    """§4 command safety rule: commands come from official documentation, tested,
    with expected output; destructive/billable effects must be declared."""
    cards = []
    for step in claim_steps or []:
        if step.get("kind") != "command":
            continue
        cards.append({
            "command": step.get("text", ""),
            "source_url": step.get("source_url") or step.get("evidence_url"),
            "shell_os": step.get("shell_os") or "document the OS/shell",
            "prerequisites": step.get("prerequisites") or [],
            "expected_output": step.get("expected_output"),
            "destructive": bool(step.get("destructive")),
            "billable": bool(step.get("billable")),
            "unsafe_reasons": _unsafe_reasons(step),
        })
    return cards


def _unsafe_reasons(step: dict) -> list[str]:
    reasons = []
    if not (step.get("source_url") or step.get("evidence_url")):
        reasons.append("no official source URL — command must be rewritten from official docs")
    if not step.get("expected_output"):
        reasons.append("expected output not documented — test in a clean environment first")
    if step.get("destructive"):
        reasons.append("DESTRUCTIVE — explain effects on camera before running")
    if step.get("billable"):
        reasons.append("BILLABLE — state the cost on camera before running")
    return reasons


def render_script_md(offer: dict, checklist: list[dict], command_cards: list[dict],
                     evidence: list[dict]) -> str:
    """Markdown script following §4/§15 sequence. Every factual claim cites
    its evidence; renewal cost is always surfaced (§11)."""
    provider = offer.get("provider", "the provider")
    title = offer.get("title", "Offer walkthrough")
    expires = _fmt_date(offer.get("expires_at"))
    renewal = decode_mapping(offer.get("renewal"))
    promo_code = offer.get("promo_code")

    lines: list[str] = []
    lines.append(f"# {title} — real claim walkthrough")
    lines.append("")
    lines.append(f"_Checked on {datetime.utcnow().strftime('%d %b %Y')}. Terms may change; "
                 "source links below and in the description._")
    lines.append("")
    lines.append(f"## Who this is for")
    lines.append(
        _eligibility_line(offer)
        + (f" Promo code: `{promo_code}`." if promo_code else "")
    )
    lines.append("")
    lines.append("## Before starting (official terms)")
    lines.append(f"- Read the official terms: {offer.get('redemption_url') or 'link in evidence below'}.")
    if expires:
        lines.append(f"- ⏰ Expires: **{expires}** — check it is still valid before you attempt this.")
    if renewal.get("autoRenew") or renewal.get("regularPrice"):
        lines.append(
            f"- ⚠️ After the free period this renews at **{renewal.get('regularPrice', 'the regular price')}** "
            f"(auto-renew: {'on' if renewal.get('autoRenew') else 'off by default'}). "
            "Show the renewal price and auto-renew setting before finalizing."
        )
    lines.append("")
    lines.append("## Claim steps (perform in real time; pause on irreversible/paid decisions)")
    for step in checklist:
        lines.append(f"{step['order'] + 1}. [{step['kind']}] {step['text']}")
    lines.append("")
    if command_cards:
        lines.append("## Commands / setup (tested; OS/shell stated)")
        for card in command_cards:
            lines.append(f"```bash\n# {card['shell_os']}\n{card['command']}\n```")
            lines.append(f"- Expected output: {card['expected_output'] or '_TODO: test in clean environment_'}")
            lines.append(f"- Source: {card['source_url'] or '_missing official source — do not film_'}")
            for reason in card["unsafe_reasons"]:
                lines.append(f"- ⚠️ {reason}")
        lines.append("")
    lines.append("## Verify the benefit")
    lines.append("- Open the provider dashboard and show exactly where the benefit landed "
                 "(plan, quota, domain panel) — no staged success screens.")
    lines.append("")
    lines.append("## Wrap-up summary card")
    lines.append(f"- Steps recap: {len(checklist)} checks above; expiry {expires or '— see terms'}; "
                 f"ongoing cost: {renewal.get('regularPrice', 'none stated')} (auto-renew).")
    lines.append("- Sources (also in video description):")
    for ev in evidence:
        lines.append(f"  - {ev.get('url')} — captured {_fmt_date(ev.get('captured_at'))}")
    lines.append("")
    lines.append("> Never imply a universal result: state region and eligibility limits again at the end.")
    return "\n".join(lines)


def _eligibility_line(offer: dict) -> str:
    eligibility = decode_mapping(offer.get("eligibility"))
    parts = []
    if eligibility.get("countries"):
        parts.append(f"Region: {', '.join(eligibility['countries'])}")
    if eligibility.get("studentStatus"):
        parts.append("students only (verification required)" if eligibility.get("verificationRequired") else "students")
    if eligibility.get("startupStatus"):
        parts.append("startups (application-based)" if eligibility.get("newCustomerOnly") is None else "startups")
    if eligibility.get("newCustomerOnly"):
        parts.append("new customers only")
    if not parts:
        return "Open eligibility — but confirm current terms on the official page before claiming."
    return " · ".join(parts) + "."


def generate(offer: dict, evidence: list[dict]) -> dict:
    """Full generation pipeline. Raises ScriptGateError for unverified offers."""
    assert_video_allowed(offer.get("state", ""))
    checklist = build_checklist(offer)
    command_cards = build_command_cards(decode_list(offer.get("claim_steps")))
    markdown = render_script_md(offer, checklist, command_cards, evidence)
    return {
        "markdown": markdown,
        "checklist": checklist,
        "command_cards": command_cards,
    }
