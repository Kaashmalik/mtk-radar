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
from offer_terms import CONTRADICTED, SUPPORTED, UNKNOWN

VIDEO_STATES: Final = frozenset({"verified", "approved_for_video", "published"})
SUPPORTED_LANGUAGES: Final = ("en", "ur")
SCRIPT_FORMATS: Final = (
    "official_explainer",
    "tested_tutorial",
    "claim_walkthrough",
)
DEFAULT_FORMAT: Final = "official_explainer"


class ScriptGateError(PermissionError):
    """Raised when script generation is attempted for an unverified offer."""


def _fact_pack(offer: dict) -> dict:
    """The server-derived fact pack for this offer's latest extraction."""
    return decode_mapping(offer.get("fact_pack"))


def _fact(name: str, offer: dict) -> dict:
    return _fact_pack(offer).get(name) or {}


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


def assert_format_allowed(script_format: str, capture: dict | None) -> None:
    """A format may only claim what the recorded evidence/capture supports.

    - official_explainer explains the published terms; it needs no capture and
      must not use first-person success wording.
    - tested_tutorial needs a capture whose redaction was reviewed by a human.
    - claim_walkthrough additionally needs that reviewer to attest the benefit
      was actually demonstrated in the footage. Footage alone is not success.
    """
    if script_format not in SCRIPT_FORMATS:
        raise ScriptGateError(
            f"unknown script format '{script_format}' — known: {', '.join(SCRIPT_FORMATS)}"
        )
    if script_format == "official_explainer":
        return
    if not capture or not capture.get("redaction_reviewed"):
        raise ScriptGateError(
            f"script format '{script_format}' requires a capture whose redaction "
            "was reviewed by a human; generate a capture first or use "
            "official_explainer"
        )
    if script_format == "claim_walkthrough" \
            and capture.get("claim_outcome") != "demonstrated":
        raise ScriptGateError(
            "claim_walkthrough requires a reviewer-attested demonstrated claim; "
            "the capture outcome is "
            f"'{capture.get('claim_outcome') or 'not recorded'}'. Use "
            "tested_tutorial or official_explainer until the outcome is demonstrated."
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


def build_beats(offer: dict, checklist: list[dict],
                script_format: str = DEFAULT_FORMAT,
                capture: dict | None = None) -> list[dict]:
    """A retention-oriented beat sheet shared by English and Urdu scripts.

    Wording follows the format: only a demonstrated claim walkthrough may say
    the claim succeeded. An explainer never speaks in the first person.
    """
    title = offer.get("title", "this offer")
    provider = offer.get("provider", "the provider")
    if script_format == "claim_walkthrough":
        hook_en = f"I claimed {title} from {provider} — here is the real proof."
        hook_ur = f"میں نے {provider} سے {title} حقیقت میں کلیم کیا — ثبوت سامنے ہے۔"
    elif script_format == "tested_tutorial":
        hook_en = f"I tested the setup steps for {title} from {provider}."
        hook_ur = f"میں نے {provider} کی {title} سیٹ اپ کے مراحل خود ٹیسٹ کیے۔"
    else:
        hook_en = f"Here is what {provider}'s official terms actually say about {title}."
        hook_ur = f"آفیشل شرائط کے مطابق {provider} کی {title} کی حقیقت یہ ہے۔"

    if script_format == "claim_walkthrough" and capture:
        result_en = "Show the demonstrated benefit in the provider account — no staged screens."
        result_ur = "پرووائیڈر اکاؤنٹ میں ثابت شدہ فائدہ دکھائیں — کوئی جعلی اسکرین نہیں۔"
    elif script_format == "tested_tutorial" and capture:
        outcome = capture.get("claim_outcome")
        if outcome == "demonstrated":
            result_en = "Show the demonstrated result, or state clearly that the benefit was not shown."
            result_ur = "ثابت شدہ نتیجہ دکھائیں، ورنہ واضح کریں کہ فائدہ نہیں دکھایا گیا۔"
        elif outcome == "not_demonstrated":
            result_en = "State that the steps ran but the benefit was not demonstrated in this test."
            result_ur = "واضح کریں کہ مراحل چلے مگر اس ٹیسٹ میں فائدہ ثابت نہیں ہوا۔"
        else:
            result_en = "State that the benefit was not attempted; this is a setup tutorial, not a result."
            result_ur = "واضح کریں کہ فائدہ آزمایا نہیں گیا؛ یہ سیٹ اپ ٹیوٹوریل ہے، نتیجہ نہیں۔"
    else:
        result_en = "Show the relevant official terms on screen; do not imply a result you did not demonstrate."
        result_ur = "متعلقہ آفیشل شرائط اسکرین پر دکھائیں؛ ایسا نتیجہ نہ دکھائیں جو ثابت نہ ہوا ہو۔"

    return [
        {"id": "hook", "at_s": 0, "purpose": "stop the scroll",
         "en": hook_en, "ur": hook_ur},
        {"id": "eligibility", "at_s": 4, "purpose": "qualify the viewer early",
         "en": _eligibility_line(offer),
         "ur": _eligibility_line_ur(offer)},
        {"id": "proof", "at_s": 9, "purpose": "show official terms on screen",
         "en": "Official terms and eligibility are on screen; the source is in the description.",
         "ur": "آفیشل شرائط اور اہلیت اسکرین پر ہیں؛ مکمل ذریعہ ڈسکرپشن میں ہے۔"},
        {"id": "claim", "at_s": 15, "purpose": "real-time claim walkthrough",
         "en": f"{len(checklist)} ordered checks, performed live on a real account."
               if script_format != "official_explainer"
               else f"{len(checklist)} ordered checks from the official terms.",
         "ur": f"{len(checklist)} مرحلے، ایک حقیقی اکاؤنٹ پر لائیو کیے گئے۔"
               if script_format != "official_explainer"
               else f"آفیشل شرائط کے {len(checklist)} مرحلے۔"},
        {"id": "result", "at_s": 45, "purpose": "show where the benefit landed",
         "en": result_en, "ur": result_ur},
        {"id": "cta", "at_s": 55, "purpose": "convert without misleading",
         "en": "Full guide, eligibility and source links are in the description.",
         "ur": "مکمل گائیڈ، اہلیت اور آفیشل لنکس ڈسکرپشن میں موجود ہیں۔"},
    ]


def render_script_md(offer: dict, checklist: list[dict], command_cards: list[dict],
                     evidence: list[dict], language: str = "en",
                     script_format: str = DEFAULT_FORMAT,
                     capture: dict | None = None) -> str:
    """Markdown script following §4/§15 sequence, in English or Urdu.

    Every factual claim cites evidence; renewal cost is always surfaced (§11).
    The format decides what the narration may assert about a demonstration.
    """
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported script language '{language}' — known: {', '.join(SUPPORTED_LANGUAGES)}")
    if script_format not in SCRIPT_FORMATS:
        raise ValueError(f"unknown script format '{script_format}'")
    if language == "ur":
        markdown = _render_ur(offer, checklist, command_cards, evidence,
                              script_format, capture)
    else:
        markdown = _render_en(offer, checklist, command_cards, evidence,
                              script_format, capture)
    assert_format_wording(markdown, script_format)
    return markdown


def assert_format_wording(markdown: str, script_format: str) -> None:
    """Belt and braces: a renderer change cannot smuggle an outcome claim in.

    v0.33: the guard now covers every language (English, Urdu script AND the
    Roman-Urdu transliteration real scripts use) and every format so a
    language swap can never become a wording-guard bypass:
    - official_explainer: NO first-person result wording — it explains
      published terms and never claims an outcome, in any language.
    - tested_tutorial: may say what was TESTED, never that a claim was
      APPROVED or a reward received — that requires the demonstrated-capture
      binding (assert_format_allowed), not just wording.
    - claim_walkthrough: documents a reviewer-attested demonstrated claim, so
      first-person wording is the point; the capture binding is the gate and
      nothing is forbidden here.
    """
    lowered = markdown.lower()

    def _forbid(phrases: list[str], reason: str) -> None:
        for phrase in phrases:
            if phrase in lowered:
                raise ScriptGateError(f"{script_format} must not use {reason} ('{phrase}')")

    if script_format == "official_explainer":
        # English + Urdu script + Roman-Urdu transliteration: a language swap
        # must not become a wording-guard bypass.
        _forbid(
            [
                # English
                "i claimed", "i tested", "i completed", "my result",
                # Urdu script (checked against the lowercased original; Urdu has
                # no case, .lower() is a no-op there)
                "میں نے کلیم کیا", "میں نے ٹیسٹ کیا", "میں نے مکمل کیا",
                "میرا نتیجہ",
                # Roman Urdu
                "maine claim kiya", "maine test kiya", "maine mukammal kiya",
                "mera nateeja", "mera result",
            ],
            "first-person result wording",
        )
    elif script_format == "tested_tutorial":
        _forbid(
            [
                # outcome/entitlement claims — a tutorial may describe testing,
                # never an approved claim or received benefit
                "claim approved", "claim was approved", "offer approved",
                "i received", "i got paid", "money arrived", "reward received",
                # Urdu script
                "کلیم منظور", "درخواست منظور", "رقم موصول", "انعام موصول",
                "پیسے مل گئے",
                # Roman Urdu
                "claim approve ho gaya", "claim manzoor ho gaya",
                "paisay mil gaye", "paise mil gaye",
            ],
            "unproven outcome wording (tested tutorials describe testing, "
            "not an approved claim)",
        )


def _render_en(offer: dict, checklist: list[dict], command_cards: list[dict],
               evidence: list[dict], script_format: str,
               capture: dict | None) -> str:
    provider = offer.get("provider", "the provider")
    title = offer.get("title", "Offer walkthrough")
    expires = _fmt_date(offer.get("expires_at"))
    renewal = decode_mapping(offer.get("renewal"))
    promo_code = offer.get("promo_code")
    outcome = capture.get("claim_outcome") if capture else None

    titles = {
        "official_explainer": "official terms explainer",
        "tested_tutorial": "tested tutorial",
        "claim_walkthrough": "real claim walkthrough",
    }
    lines: list[str] = []
    lines.append(f"# {title} — {titles[script_format]}")
    lines.append("")
    lines.append(f"_Checked on {datetime.utcnow().strftime('%d %b %Y')}. Terms may change; "
                 "source links below and in the description._")
    lines.append("")
    lines.append(f"> Format: `{script_format}`. "
                 + ("This explains the published terms; it does not claim a successful result."
                    if script_format == "official_explainer"
                    else "Wording is limited to what the reviewed capture supports."))
    lines.append("")
    lines.append("## Hook options (choose one, keep it under 3 seconds)")
    if script_format == "claim_walkthrough":
        lines.append(f"1. I claimed **{title}** from {provider} — here is the real proof.")
        lines.append(f"2. This {provider} offer looks too good to be true — I tested the real claim.")
        lines.append(f"3. Do not pay for {title} until you see what the official terms actually say.")
    elif script_format == "tested_tutorial":
        lines.append(f"1. I tested the setup steps for **{title}** from {provider}.")
        lines.append(f"2. Here is exactly how the {provider} setup works — and where it can fail.")
        lines.append(f"3. Before you try {title}, check these steps and the current terms.")
    else:
        lines.append(f"1. Here is what {provider}'s official terms actually say about **{title}**.")
        lines.append(f"2. Before you trust {title}, read these exact terms with me.")
        lines.append(f"3. No hype: the official rules, eligibility and unknowns for {title}.")
    lines.append("")
    lines.append("## Who this is for")
    lines.append(
        _eligibility_line(offer)
        + (f" Promo code: `{promo_code}`." if promo_code else "")
    )
    lines.append("")
    lines.append("## Before starting (official terms)")
    lines.append(f"- Read the official terms: {offer.get('redemption_url') or 'link in evidence below'}.")
    if expires:
        lines.append(f"- ⏰ Expires: **{expires}** — check it is still valid before you attempt this.")
    else:
        # "No expiry stated" is not "never expires" (§6 step 7).
        expiry_status = _fact("expiry", offer).get("status")
        if expiry_status == SUPPORTED:
            lines.append(f"- ⏰ {NO_EXPIRY_STATED.capitalize()} in the checked evidence, "
                         "but the offer is currently verified — recheck before filming.")
        else:
            lines.append(f"- ⏰ {NO_EXPIRY_STATED.capitalize()} — this is not proof the offer "
                         "never expires. Confirm the deadline on the official page.")
    if renewal.get("regularPrice"):
        lines.append(
            f"- ⚠️ After the free period this renews at **{renewal.get('regularPrice')}** "
            f"(auto-renew: {'on' if renewal.get('autoRenew') else 'off by default'}). "
            "Show the renewal price and auto-renew setting before finalizing."
        )
    else:
        renewal_status = _fact("renewal", offer).get("status")
        if renewal_status == CONTRADICTED:
            lines.append("- ⚠️ The quoted official terms contradict this offer's renewal claim — "
                         "manual review is required before filming or recommending it.")
        else:
            lines.append(f"- ⚠️ Ongoing cost {ONGOING_COST_UNKNOWN}. Unknown renewal is not free — "
                         "state the cost on camera or confirm the terms before recommending the offer.")
    lines.append("")
    if script_format == "official_explainer":
        lines.append("## Steps described in the official terms")
    else:
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
    if script_format == "claim_walkthrough":
        lines.append("## Demonstrated benefit")
        lines.append("- Open the provider dashboard and show exactly where the benefit landed "
                     "(plan, quota, domain panel) — no staged success screens.")
    elif script_format == "tested_tutorial":
        lines.append("## Test result (word this exactly as recorded)")
        if outcome == "demonstrated":
            lines.append("- The reviewed capture demonstrates the benefit. Show the same evidence "
                         "on screen and state the eligibility limits.")
        elif outcome == "not_demonstrated":
            lines.append("- The reviewed capture completed the steps but did NOT demonstrate the "
                         "benefit. Say that clearly; do not imply success.")
        else:
            lines.append("- The reviewed capture did not attempt the benefit. This is a setup "
                         "tutorial; do not imply that the benefit was obtained.")
    else:
        lines.append("## What the official terms say about the benefit")
        lines.append("- Quote the official benefit wording and show it on screen. Unknown or "
                     "unstated facts stay unknown; do not imply a demonstrated result.")
    lines.append("")
    lines.append("## CTA")
    lines.append("- Full guide, eligibility and official source links are in the description. "
                 "Use the tracked website link, not a lookalike domain.")
    lines.append("")
    lines.append("## Wrap-up summary card")
    lines.append(f"- Steps recap: {len(checklist)} checks above; "
                 f"deadline: {expires or NO_EXPIRY_STATED}; "
                 f"ongoing cost: {renewal.get('regularPrice') or ONGOING_COST_UNKNOWN}"
                 + (" (" if renewal.get("regularPrice") and renewal.get("autoRenew") else "")
                 + ("auto-renew on" if renewal.get("regularPrice") and renewal.get("autoRenew") else "")
                 + (")" if renewal.get("regularPrice") and renewal.get("autoRenew") else "")
                 + ("" if renewal.get("regularPrice") else " — unknown renewal is not free")
                 + ".")
    lines.append("- Sources (also in video description):")
    for ev in evidence:
        lines.append(f"  - {ev.get('url')} — captured {_fmt_date(ev.get('captured_at'))}")
    lines.append("")
    lines.append("> Never imply a universal result: state region and eligibility limits again at the end.")
    return "\n".join(lines)


#: Truthful unknown wording (§6 step 7, A13). An unknown fact never becomes
#: "open eligibility", "free", "worldwide" or "never expires".
NO_EXPIRY_STATED: Final = "no expiry stated in the inspected terms"
ELIGIBILITY_UNKNOWN: Final = (
    "Eligibility is not stated in the inspected terms — confirm the current "
    "audience on the official page. Do not present this offer as open to everyone."
)
ONGOING_COST_UNKNOWN: Final = "not stated in the inspected terms"


def _render_ur(offer: dict, checklist: list[dict], command_cards: list[dict],
               evidence: list[dict], script_format: str,
               capture: dict | None) -> str:
    provider = offer.get("provider", "پرووائیڈر")
    title = offer.get("title", "آفر")
    expires = _fmt_date(offer.get("expires_at"))
    renewal = decode_mapping(offer.get("renewal"))
    promo_code = offer.get("promo_code")
    outcome = capture.get("claim_outcome") if capture else None

    titles = {
        "official_explainer": "آفیشل شرائط کی وضاحت",
        "tested_tutorial": "ٹیسٹ شدہ ٹیوٹوریل",
        "claim_walkthrough": "اصلی کلیم گائیڈ",
    }
    lines: list[str] = []
    lines.append(f"# {title} — {titles[script_format]}")
    lines.append("")
    lines.append(f"_چیک کیا گیا: {datetime.utcnow().strftime('%d %b %Y')}۔ شرائط بدل سکتی ہیں؛ "
                 "ذرائع نیچے اور ڈسکرپشن میں موجود ہیں۔_")
    lines.append("")
    lines.append(f"> فارمیٹ: `{script_format}`۔ "
                 + ("یہ صرف شائع شدہ شرائط کی وضاحت ہے؛ کامیابی کا دعویٰ نہیں۔"
                    if script_format == "official_explainer"
                    else "الفاظ صرف ریویو شدہ ریکارڈنگ تک محدود ہیں۔"))
    lines.append("")
    lines.append("## ہک کے آپشن (ایک منتخب کریں، 3 سیکنڈ سے کم رکھیں)")
    if script_format == "claim_walkthrough":
        lines.append(f"1. میں نے {provider} سے **{title}** حقیقت میں کلیم کیا — ثبوت سامنے ہے۔")
        lines.append(f"2. یہ {provider} آفر بہت اچھی لگ رہی ہے — میں نے اصلی کلیم ٹیسٹ کیا۔")
        lines.append(f"3. {title} پر پیسے خرچ کرنے سے پہلے آفیشل شرائط ضرور دیکھیں۔")
    elif script_format == "tested_tutorial":
        lines.append(f"1. میں نے {provider} کی **{title}** سیٹ اپ کے مراحل خود ٹیسٹ کیے۔")
        lines.append("2. یہ مرحلہ وار سیٹ اپ ہے — اور یہاں کہاں غلطی ہو سکتی ہے۔")
        lines.append(f"3. {title} آزمانے سے پہلے یہ مراحل اور موجودہ شرائط دیکھیں۔")
    else:
        lines.append(f"1. {provider} کی آفیشل شرائط **{title}** کے بارے میں اصل کیا کہتی ہیں؟")
        lines.append(f"2. {title} پر بھروسہ کرنے سے پہلے یہ شرائط میرے ساتھ پڑھیں۔")
        lines.append(f"3. بغیر مبالغے کے: آفیشل قواعد، اہلیت اور غیر واضح نکات۔")
    lines.append("")
    lines.append("## یہ کس کے لیے ہے")
    lines.append(_eligibility_line_ur(offer)
                 + (f" پرومو کوڈ: `{promo_code}`۔" if promo_code else ""))
    lines.append("")
    lines.append("## شروع کرنے سے پہلے (آفیشل شرائط)")
    lines.append(f"- آفیشل شرائط پڑھیں: {offer.get('redemption_url') or 'نیچے ذرائع میں لنک'}۔")
    if expires:
        lines.append(f"- ⏰ آخری تاریخ: **{expires}** — کوشش سے پہلے تصدیق کریں کہ آفر ابھی فعال ہے۔")
    else:
        # §6 قدم 7: 'آخری تاریخ درج نہیں' کا مطلب 'کبھی ختم نہیں ہوتی' نہیں —
        # اردو سطر انگریزی وارننگ کا ہم آہنگ ہے۔
        expiry_status = _fact("expiry", offer).get("status")
        if expiry_status == SUPPORTED:
            lines.append("- ⏰ چیک شدہ شرائط میں آخری تاریخ درج نہیں، مگر آفر فی الحال "
                         "تصدیق شدہ ہے — فلم بنانے سے پہلے دوبارہ چیک کریں۔")
        else:
            lines.append("- ⏰ آخری تاریخ درج نہیں — یہ اس بات کا ثبوت نہیں کہ آفر کبھی "
                         "ختم نہیں ہوتی۔ آفیشل صفحے پر آخری تاریخ ضرور تصدیق کریں۔")
    if renewal.get("regularPrice"):
        lines.append(
            f"- ⚠️ مفت مدت کے بعد قیمت **{renewal.get('regularPrice')}** ہوگی "
            f"(خودکار تجدید: {'آن' if renewal.get('autoRenew') else 'آف (ڈیفالٹ)'})۔ "
            "فائنل کرنے سے پہلے قیمت اور خودکار تجدید اسکرین پر دکھائیں۔"
        )
    else:
        # انگریزی برانچ کا ہم آہنگ: کوئی قیمت درج نہ ہو تو کوئی قیمت مت گھڑیں —
        # 'عام قیمت' بھی ایک قیمت کا دعویٰ ہے۔
        renewal_status = _fact("renewal", offer).get("status")
        if renewal_status == CONTRADICTED:
            lines.append("- ⚠️ نقل شدہ آفیشل شرائط اس آفر کی تجدید کے دعوے کے خلاف ہیں — "
                         "فلم بنانے یا سفارش سے پہلے دستی ریویو ضروری ہے۔")
        else:
            lines.append("- ⚠️ جاری قیمت چیک شدہ شرائط میں درج نہیں۔ نامعلوم تجدید مفت "
                         "نہیں ہوتی — کیمرے پر قیمت بتائیں یا شرائط کی تصدیق کریں۔")
    lines.append("")
    if script_format == "official_explainer":
        lines.append("## آفیشل شرائط میں بیان کردہ مراحل")
    else:
        lines.append("## کلیم کے مراحل (لائیو کریں؛ ناقابلِ واپسی یا ادائیگی والے قدم پر رکیں)")
    for step in checklist:
        lines.append(f"{step['order'] + 1}. [{step['kind']}] {step['text']}")
    lines.append("")
    if command_cards:
        lines.append("## کمانڈز / سیٹ اپ (ٹیسٹ شدہ؛ OS/شیل واضح)")
        for card in command_cards:
            lines.append(f"```bash\n# {card['shell_os']}\n{card['command']}\n```")
            lines.append(f"- متوقع نتیجہ: {card['expected_output'] or '_TODO: صاف ماحول میں ٹیسٹ کریں_'}")
            lines.append(f"- ذریعہ: {card['source_url'] or '_آفیشل ذریعہ نہیں — فلم نہ کریں_'}")
            for reason in card["unsafe_reasons"]:
                lines.append(f"- ⚠️ {reason}")
        lines.append("")
    if script_format == "claim_walkthrough":
        lines.append("## ثابت شدہ فائدہ")
        lines.append("- پرووائیڈر ڈیش بورڈ کھولیں اور دکھائیں کہ فائدہ کہاں پہنچا "
                     "(پلان، کوٹہ، ڈومین پینل) — کوئی جعلی کامیابی اسکرین نہیں۔")
    elif script_format == "tested_tutorial":
        lines.append("## ٹیسٹ کا نتیجہ (ٹھیک اسی طرح بیان کریں)")
        if outcome == "demonstrated":
            lines.append("- ریویو شدہ ریکارڈنگ فائدہ ثابت کرتی ہے۔ وہی ثبوت اسکرین پر دکھائیں۔")
        elif outcome == "not_demonstrated":
            lines.append("- مراحل مکمل ہوئے مگر فائدہ ثابت نہیں ہوا۔ صاف کہیں؛ کامیابی کا تاثر نہ دیں۔")
        else:
            lines.append("- فائدہ آزمایا ہی نہیں گیا۔ یہ سیٹ اپ ٹیوٹوریل ہے؛ کامیابی کا دعویٰ نہ کریں۔")
    else:
        lines.append("## آفیشل شرائط فائدے کے بارے میں کیا کہتی ہیں")
        lines.append("- آفیشل الفاظ نقل کریں اور اسکرین پر دکھائیں۔ غیر واضح بات غیر واضح رہے۔")
    lines.append("")
    lines.append("## CTA")
    lines.append("- مکمل گائیڈ، اہلیت اور آفیشل لنکس ڈسکرپشن میں ہیں۔ "
                 "ٹریک شدہ ویب سائٹ لنک استعمال کریں، ملتا جلتا ڈومین نہیں۔")
    lines.append("")
    lines.append("## اختتامی خلاصہ")
    if renewal.get("autoRenew") is None:
        auto_renew_ur = "درج نہیں"
    else:
        auto_renew_ur = "آن" if renewal.get("autoRenew") else "آف"
    lines.append(f"- مراحل: اوپر {len(checklist)} چیک؛ آخری تاریخ {expires or '— شرائط دیکھیں'}؛ "
                 f"جاری قیمت: {renewal.get('regularPrice') or 'درج نہیں'}؛ "
                 f"خودکار تجدید: {auto_renew_ur}۔")
    lines.append("- ذرائع (ویڈیو ڈسکرپشن میں بھی):")
    for ev in evidence:
        lines.append(f"  - {ev.get('url')} — ریکارڈ شدہ {_fmt_date(ev.get('captured_at'))}")
    lines.append("")
    lines.append("> عالمی نتیجہ ہرگز نہ دکھائیں: آخر میں علاقہ اور اہلیت کی حدود دوبارہ بتائیں۔")
    return "\n".join(lines)


def _eligibility_line(offer: dict) -> str:
    eligibility = decode_mapping(offer.get("eligibility"))
    parts = []
    if eligibility.get("countries"):
        parts.append(f"Region: {', '.join(eligibility['countries'])}")
    if eligibility.get("studentStatus"):
        parts.append("students only (verification required)" if eligibility.get("verificationRequired") else "students")
    if eligibility.get("startupStatus"):
        # "(application-based)" claims a specific application process — it must
        # come from a real application signal (the benefit_type fact), never
        # from an unrelated field like newCustomerOnly.
        application_based = (str(_fact("benefit_type", offer).get("value") or "")
                             .strip().lower() == "application_based"
                             or bool(eligibility.get("requiresApplication")))
        parts.append("startups (application-based)" if application_based else "startups")
    if eligibility.get("newCustomerOnly"):
        parts.append("new customers only")
    if not parts:
        status = _fact("eligibility", offer).get("status")
        if status == CONTRADICTED:
            return ("The quoted official terms contradict this offer's eligibility — "
                    "manual review is required before filming.")
        if status == UNKNOWN:
            return ELIGIBILITY_UNKNOWN
        return ("No audience limit is recorded in the official evidence "
                "(not proof that the offer is open to everyone) — confirm current terms."
                if status == SUPPORTED else ELIGIBILITY_UNKNOWN)
    return " · ".join(parts) + "."


def _eligibility_line_ur(offer: dict) -> str:
    eligibility = decode_mapping(offer.get("eligibility"))
    parts = []
    if eligibility.get("countries"):
        parts.append(f"علاقہ: {', '.join(eligibility['countries'])}")
    if eligibility.get("studentStatus"):
        parts.append("صرف طلبہ (تصدیق ضروری)" if eligibility.get("verificationRequired") else "طلبہ")
    if eligibility.get("startupStatus"):
        # اردو سطر انگریزی کے ساتھ ہم آہنگ ہونی چاہیے: '(درخواست کے ذریعے)' صرف
        # اسی وقت جب اصل درخواستی سگنل موجود ہو۔
        application_based = (str(_fact("benefit_type", offer).get("value") or "")
                             .strip().lower() == "application_based"
                             or bool(eligibility.get("requiresApplication")))
        parts.append("اسٹارٹ اپس (درخواست کے ذریعے)" if application_based else "اسٹارٹ اپس")
    if eligibility.get("newCustomerOnly"):
        parts.append("صرف نئے صارفین")
    if not parts:
        # A13/ur: ایک نامعلوم یا متنازع اہلیت کبھی 'کھلی اہلیت' نہیں لکھی جا سکتی —
        # انگریزی برانچ کی طرح حیثیت کے مطابق لکھیں۔
        status = _fact("eligibility", offer).get("status")
        if status == CONTRADICTED:
            return ("نقل شدہ آفیشل شرائط اس آفر کی اہلیت کے خلاف جاتی ہیں — فلم بنانے "
                    "یا سفارش سے پہلے دستی ریویو ضروری ہے۔")
        if status == SUPPORTED:
            return ("آفیشل شواہد میں سامعین کی کوئی حد درج نہیں (یہ اس بات کا ثبوت "
                    "نہیں کہ آفر سب کے لیے کھلی ہے) — موجودہ شرائط کی تصدیق کریں۔")
        return ("اہلیت چیک شدہ شرائط میں درج نہیں — آفیشل صفحے پر موجودہ شرائط "
                "ضرور دیکھیں۔ اس آفر کو ہر کسی کے لیے کھلی نہ بتائیں۔")
    return " · ".join(parts) + "۔"


def generate(offer: dict, evidence: list[dict], language: str = "en",
             script_format: str = DEFAULT_FORMAT,
             capture: dict | None = None) -> dict:
    """Full generation pipeline. Raises ScriptGateError for unverified offers."""
    assert_video_allowed(offer.get("state", ""))
    assert_format_allowed(script_format, capture)
    checklist = build_checklist(offer)
    command_cards = build_command_cards(decode_list(offer.get("claim_steps")))
    markdown = render_script_md(
        offer, checklist, command_cards, evidence, language=language,
        script_format=script_format, capture=capture,
    )
    return {
        "markdown": markdown,
        "checklist": checklist,
        "command_cards": command_cards,
        "language": language,
        "format": script_format,
        "beats": build_beats(offer, checklist, script_format, capture),
    }


def generate_multilingual(offer: dict, evidence: list[dict],
                          languages: tuple[str, ...] = SUPPORTED_LANGUAGES,
                          script_format: str = DEFAULT_FORMAT,
                          capture: dict | None = None) -> dict:
    """Generate every requested language from the same verified facts."""
    if not languages:
        raise ValueError("at least one language is required")
    for language in languages:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language '{language}' — known: {', '.join(SUPPORTED_LANGUAGES)}")
    if script_format not in SCRIPT_FORMATS:
        raise ValueError(f"unknown script format '{script_format}'")
    generated = {
        language: generate(offer, evidence, language=language,
                           script_format=script_format, capture=capture)
        for language in languages
    }
    return {
        "languages": generated,
        "beats": generated[languages[0]]["beats"],
        "format": script_format,
    }
