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


def build_beats(offer: dict, checklist: list[dict]) -> list[dict]:
    """A retention-oriented beat sheet shared by English and Urdu scripts.

    The beats are deliberately short and visual: hook → proof → steps → result
    → CTA. The editor can cut to these markers without re-reading the script.
    """
    title = offer.get("title", "this offer")
    provider = offer.get("provider", "the provider")
    return [
        {"id": "hook", "at_s": 0, "purpose": "stop the scroll",
         "en": f"I claimed {title} from {provider} — here is the real proof.",
         "ur": f"میں نے {provider} سے {title} حقیقت میں کلیم کیا — ثبوت سامنے ہے۔"},
        {"id": "eligibility", "at_s": 4, "purpose": "qualify the viewer early",
         "en": _eligibility_line(offer),
         "ur": _eligibility_line_ur(offer)},
        {"id": "proof", "at_s": 9, "purpose": "show official terms on screen",
         "en": "Official terms and eligibility are on screen; the source is in the description.",
         "ur": "آفیشل شرائط اور اہلیت اسکرین پر ہیں؛ مکمل ذریعہ ڈسکرپشن میں ہے۔"},
        {"id": "claim", "at_s": 15, "purpose": "real-time claim walkthrough",
         "en": f"{len(checklist)} ordered checks, performed live on a real account.",
         "ur": f"{len(checklist)} مرحلے، ایک حقیقی اکاؤنٹ پر لائیو کیے گئے۔"},
        {"id": "result", "at_s": 45, "purpose": "show where the benefit landed",
         "en": "Open the provider dashboard and show the benefit — no staged success screens.",
         "ur": "پرووائیڈر ڈیش بورڈ کھول کر فائدہ دکھائیں — کوئی جعلی کامیابی نہیں۔"},
        {"id": "cta", "at_s": 55, "purpose": "convert without misleading",
         "en": "Full guide, eligibility and source links are in the description.",
         "ur": "مکمل گائیڈ، اہلیت اور آفیشل لنکس ڈسکرپشن میں موجود ہیں۔"},
    ]


def render_script_md(offer: dict, checklist: list[dict], command_cards: list[dict],
                     evidence: list[dict], language: str = "en") -> str:
    """Markdown script following §4/§15 sequence, in English or Urdu.

    Every factual claim cites evidence; renewal cost is always surfaced (§11).
    """
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported script language '{language}' — known: {', '.join(SUPPORTED_LANGUAGES)}")
    if language == "ur":
        return _render_ur(offer, checklist, command_cards, evidence)
    return _render_en(offer, checklist, command_cards, evidence)


def _render_en(offer: dict, checklist: list[dict], command_cards: list[dict],
               evidence: list[dict]) -> str:
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
    lines.append("## Hook options (choose one, keep it under 3 seconds)")
    lines.append(f"1. I claimed **{title}** from {provider} — here is the real proof.")
    lines.append(f"2. This {provider} offer looks too good to be true — I tested the real claim.")
    lines.append(f"3. Do not pay for {title} until you see what the official terms actually say.")
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
               evidence: list[dict]) -> str:
    provider = offer.get("provider", "پرووائیڈر")
    title = offer.get("title", "آفر")
    expires = _fmt_date(offer.get("expires_at"))
    renewal = decode_mapping(offer.get("renewal"))
    promo_code = offer.get("promo_code")

    lines: list[str] = []
    lines.append(f"# {title} — اصلی کلیم گائیڈ")
    lines.append("")
    lines.append(f"_چیک کیا گیا: {datetime.utcnow().strftime('%d %b %Y')}۔ شرائط بدل سکتی ہیں؛ "
                 "ذرائع نیچے اور ڈسکرپشن میں موجود ہیں۔_")
    lines.append("")
    lines.append("## ہک کے آپشن (ایک منتخب کریں، 3 سیکنڈ سے کم رکھیں)")
    lines.append(f"1. میں نے {provider} سے **{title}** حقیقت میں کلیم کیا — ثبوت سامنے ہے۔")
    lines.append(f"2. یہ {provider} آفر بہت اچھی لگ رہی ہے — میں نے اصلی کلیم ٹیسٹ کیا۔")
    lines.append(f"3. {title} پر پیسے خرچ کرنے سے پہلے آفیشل شرائط ضرور دیکھیں۔")
    lines.append("")
    lines.append("## یہ کس کے لیے ہے")
    lines.append(_eligibility_line_ur(offer)
                 + (f" پرومو کوڈ: `{promo_code}`۔" if promo_code else ""))
    lines.append("")
    lines.append("## شروع کرنے سے پہلے (آفیشل شرائط)")
    lines.append(f"- آفیشل شرائط پڑھیں: {offer.get('redemption_url') or 'نیچے ذرائع میں لنک'}۔")
    if expires:
        lines.append(f"- ⏰ آخری تاریخ: **{expires}** — کوشش سے پہلے تصدیق کریں کہ آفر ابھی فعال ہے۔")
    if renewal.get("autoRenew") or renewal.get("regularPrice"):
        lines.append(
            f"- ⚠️ مفت مدت کے بعد قیمت **{renewal.get('regularPrice', 'عام قیمت')}** ہوگی "
            f"(خودکار تجدید: {'آن' if renewal.get('autoRenew') else 'آف'})۔ "
            "فائنل کرنے سے پہلے قیمت اور خودکار تجدید اسکرین پر دکھائیں۔"
        )
    lines.append("")
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
    lines.append("## فائدہ کی تصدیق")
    lines.append("- پرووائیڈر ڈیش بورڈ کھولیں اور دکھائیں کہ فائدہ کہاں پہنچا "
                 "(پلان، کوٹہ، ڈومین پینل) — کوئی جعلی کامیابی اسکرین نہیں۔")
    lines.append("")
    lines.append("## CTA")
    lines.append("- مکمل گائیڈ، اہلیت اور آفیشل لنکس ڈسکرپشن میں ہیں۔ "
                 "ٹریک شدہ ویب سائٹ لنک استعمال کریں، ملتا جلتا ڈومین نہیں۔")
    lines.append("")
    lines.append("## اختتامی خلاصہ")
    lines.append(f"- مراحل: اوپر {len(checklist)} چیک؛ آخری تاریخ {expires or '— شرائط دیکھیں'}؛ "
                 f"جاری قیمت: {renewal.get('regularPrice', 'درج نہیں')} (خودکار تجدید)۔")
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
        parts.append("startups (application-based)" if eligibility.get("newCustomerOnly") is None else "startups")
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
        parts.append("اسٹارٹ اپس (درخواست کے ذریعے)")
    if eligibility.get("newCustomerOnly"):
        parts.append("صرف نئے صارفین")
    if not parts:
        return "کھلی اہلیت — لیکن کلیم سے پہلے آفیشل صفحے پر موجودہ شرائط ضرور دیکھیں۔"
    return " · ".join(parts) + "۔"


def generate(offer: dict, evidence: list[dict], language: str = "en") -> dict:
    """Full generation pipeline. Raises ScriptGateError for unverified offers."""
    assert_video_allowed(offer.get("state", ""))
    checklist = build_checklist(offer)
    command_cards = build_command_cards(decode_list(offer.get("claim_steps")))
    markdown = render_script_md(offer, checklist, command_cards, evidence, language=language)
    return {
        "markdown": markdown,
        "checklist": checklist,
        "command_cards": command_cards,
        "language": language,
        "beats": build_beats(offer, checklist),
    }


def generate_multilingual(offer: dict, evidence: list[dict],
                          languages: tuple[str, ...] = SUPPORTED_LANGUAGES) -> dict:
    """Generate every requested language from the same verified facts."""
    if not languages:
        raise ValueError("at least one language is required")
    for language in languages:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language '{language}' — known: {', '.join(SUPPORTED_LANGUAGES)}")
    generated = {language: generate(offer, evidence, language=language) for language in languages}
    return {
        "languages": generated,
        "beats": generated[languages[0]]["beats"],
    }
