"""The one authoritative release check (§17 / audit P0 "release gate").

Before this module existed, "may this post go out?" was answered three
different ways — API schedule validation, the offer-freshness helper, and
ad-hoc checks inside the publishing worker — and they disagreed (the worker
failed open on a NULL `recheck_at`; upload authorization did not re-check
freshness at all).

`release_problems()` is now the single source of truth. It returns a list of
structured problems; an EMPTY list is the only permission to release.

Every check FAILS CLOSED: missing data is a problem, never a pass.
"""

from __future__ import annotations

import json
import uuid

from offer_freshness import freshness_problem
from schedules_state import script_version_hash

#: Offer states from which a release may be attempted. Anything else needs a
#: human re-verification first — a declined/expired offer must not ship.
PUBLISHABLE_OFFER_STATES = ("verified", "approved_for_video")


def _json_value(value, default):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value if value is not None else default


def _problem(code: str, detail: str) -> dict:
    return {"code": code, "detail": detail, "blocking": True}


async def offer_problems(pool, offer_id) -> list[dict]:
    """Offer state + freshness. Shared by schedule transitions (which call
    `_schedule_offer_problem`) and by the full release check, so there is one
    freshness implementation, not three."""
    row = await pool.fetchrow(
        "SELECT state::text AS state FROM offers WHERE id = $1", offer_id,
    )
    if row is None:
        return [_problem("offer_missing", "offer not found")]
    if row["state"] not in PUBLISHABLE_OFFER_STATES:
        return [_problem(
            "offer_state",
            f"offer state is '{row['state']}' — needs re-verification and "
            "approval for video before release",
        )]
    freshness = await freshness_problem(pool, offer_id)
    if freshness:
        return [_problem("offer_freshness", freshness)]
    return []


async def release_problems(pool, schedule_id: uuid.UUID) -> list[dict]:
    """Everything that blocks releasing this scheduled post, right now."""
    schedule = await pool.fetchrow(
        """
        SELECT id, state::text AS state, offer_id, platform, language, render_id,
               version_hash, metadata_hash, cover_path, cover_sha256,
               captions_sha256, render_sha256, outcome_detail::text AS outcome_detail,
               content_variant_id
        FROM schedules WHERE id = $1
        """,
        schedule_id,
    )
    if schedule is None:
        return [_problem("schedule_missing", "schedule not found")]

    problems: list[dict] = []

    problems.extend(await offer_problems(pool, schedule["offer_id"]))

    # ---- pinned render integrity -----------------------------------------
    render = None
    if schedule["render_id"]:
        render = await pool.fetchrow(
            """
            SELECT id, offer_id, language, status, qc_status, capture_id,
                   script_version_hash, video_sha256, cover_path, captions_path,
                   cover_sha256, captions_sha256, playback_approved,
                   playback_reviewer
            FROM renders WHERE id = $1
            """,
            schedule["render_id"],
        )
        if render is None:
            problems.append(_problem(
                "render_missing",
                "the pinned render no longer exists — re-render and re-schedule",
            ))
    else:
        problems.append(_problem(
            "render_missing", "the schedule has no pinned render",
        ))

    if render is not None:
        if render["offer_id"] != schedule["offer_id"]:
            problems.append(_problem(
                "offer_mismatch", "the pinned render belongs to a different offer",
            ))
        if render["status"] != "rendered" or render["qc_status"] != "passed":
            problems.append(_problem(
                "render_qc",
                f"the pinned render is {render['status']}/{render['qc_status']} — "
                "only a measured, QC-passed export may be released",
            ))
        if not schedule["version_hash"]:
            problems.append(_problem(
                "script_hash", "the schedule has no approved script hash",
            ))
        elif render["script_version_hash"] != schedule["version_hash"]:
            problems.append(_problem(
                "script_hash",
                "the pinned render was made from a different script version than "
                "the one approved — re-render the current script",
            ))
        if (schedule["language"] and render["language"]
                and render["language"] != schedule["language"]):
            problems.append(_problem(
                "language_mismatch",
                f"pinned render language '{render['language']}' does not match "
                f"the schedule language '{schedule['language']}'",
            ))
        if (schedule["render_sha256"] and render["video_sha256"]
                and str(schedule["render_sha256"]) != str(render["video_sha256"])):
            problems.append(_problem(
                "render_bytes_changed",
                "the pinned render file's hash no longer matches the approved "
                "package — re-render and re-approve",
            ))

        # ---- format/claim binding -----------------------------------------
        # The approval pinned script bytes; re-read the script's declared
        # format and make sure the evidence still supports it. A
        # claim_walkthrough is only honest if the recorded outcome was an
        # actual demonstration.
        script_row = None
        if schedule["version_hash"]:
            script_rows = await pool.fetch(
                "SELECT format, markdown FROM offer_scripts "
                "WHERE offer_id = $1 ORDER BY version DESC LIMIT 50",
                schedule["offer_id"],
            )
            for row in script_rows:
                if (row["markdown"] and script_version_hash(row["markdown"])
                        == schedule["version_hash"]):
                    script_row = row
                    break
        capture = None
        if render["capture_id"]:
            capture = await pool.fetchrow(
                "SELECT redaction_reviewed, claim_outcome FROM capture_sessions "
                "WHERE id = $1",
                render["capture_id"],
            )
        if script_row is not None:
            declared_format = script_row["format"]
            if declared_format == "claim_walkthrough":
                outcome = capture.get("claim_outcome") if capture else None
                if outcome != "demonstrated":
                    problems.append(_problem(
                        "claim_outcome",
                        "the script format is 'claim_walkthrough' but the bound "
                        "capture is not a recorded demonstration — regenerate the "
                        "script or re-record the capture",
                    ))
            if declared_format in ("tested_tutorial", "claim_walkthrough"):
                if not capture or not capture["redaction_reviewed"]:
                    problems.append(_problem(
                        "capture_review",
                        "the script format requires a redaction-reviewed capture",
                    ))

        # ---- mandatory package assets (plan §5) ----------------------------
        policy = await _release_policy(pool)
        if policy["require_package_assets"] and schedule["platform"] == "youtube":
            missing = []
            if not (schedule["cover_path"] or render["cover_path"]):
                missing.append("thumbnail")
            if not (schedule["cover_sha256"] or render["cover_sha256"]):
                missing.append("thumbnail hash")
            # Captions need an actual FILE path to upload (the schedule pins
            # the hash; the path lives on the render).
            if not render["captions_path"]:
                missing.append("captions")
            if not (render["captions_sha256"] or schedule["captions_sha256"]):
                missing.append("captions hash")
            if not schedule["metadata_hash"]:
                missing.append("approved metadata")
            if missing:
                problems.append(_problem(
                    "package_incomplete",
                    "YouTube release is missing mandatory package parts: "
                    + ", ".join(missing),
                ))

            # ---- 2026 packaging quality rules ---------------------------------
            # The metadata must be *watchable on a phone*: a ~50-character
            # title (mobile truncation), 5-8 plain search tags (YouTube says
            # tags barely matter and penalizes misleading ones), and thumbnail
            # wording of at most 3 words that does not repeat the title.
            variant = None
            if schedule["content_variant_id"]:
                variant = await pool.fetchrow(
                    "SELECT kind, payload::text AS payload FROM content_variants "
                    "WHERE id = $1",
                    schedule["content_variant_id"],
                )
                if variant is None:
                    problems.append(_problem(
                        "metadata_variant_missing",
                        "the pinned metadata variant no longer exists — "
                        "re-schedule from the studio",
                    ))
                elif variant["kind"] == "metadata":
                    payload = _json_value(variant["payload"], {})
                    title = str(payload.get("title") or "").strip()
                    if not title:
                        problems.append(_problem(
                            "metadata_title_missing",
                            "the approved metadata has no title",
                        ))
                    elif len(title) > 50:
                        problems.append(_problem(
                            "metadata_title_too_long",
                            f"packaging title is {len(title)} characters — keep "
                            "YouTube titles within 50 so the hook survives "
                            "mobile truncation",
                        ))
                    tags = payload.get("tags")
                    if not isinstance(tags, list) or not (5 <= len(tags) <= 8):
                        problems.append(_problem(
                            "metadata_tags_invalid",
                            "YouTube tags must be 5-8 plain search keywords "
                            "(1 broad + 2-4 specific + the channel name)",
                        ))
                    if any(str(tag).lstrip().startswith("#") for tag in tags):
                        problems.append(_problem(
                            "metadata_tags_hashtags",
                            "YouTube tags must be plain keywords without '#' — "
                            "hashtags belong in the description",
                        ))
            cover_variant = await pool.fetchrow(
                "SELECT payload::text AS payload FROM content_variants "
                "WHERE offer_id = $1 AND kind = 'cover' AND status = 'approved' "
                "ORDER BY version DESC LIMIT 1",
                schedule["offer_id"],
            )
            if cover_variant:
                thumb_text = str(
                    (_json_value(cover_variant["payload"], {}) or {}).get("thumbnail_text")
                    or ""
                ).strip()
                if thumb_text and len(thumb_text.split()) > 3:
                    problems.append(_problem(
                        "thumbnail_text_too_long",
                        f"approved thumbnail text is {len(thumb_text.split())} "
                        "words — keep it at most 3 words, readable on a phone",
                    ))

        # ---- final human playback review ----------------------------------
        if policy["require_playback_review"] and not render["playback_approved"]:
            problems.append(_problem(
                "playback_review",
                "no human has signed off playback of this final export "
                "(review desk → playback review)",
            ))

    # ---- duplicate protection ---------------------------------------------
    detail = _json_value(schedule["outcome_detail"], {})
    open_attempt = detail.get("attempt") if isinstance(detail, dict) else None
    if isinstance(open_attempt, dict):
        problems.append(_problem(
            "open_attempt",
            f"an upload attempt is open (leased until "
            f"{open_attempt.get('lease_expires_at')}) — verify the platform "
            "before releasing",
        ))

    return problems


async def _release_policy(pool) -> dict:
    from settings_store import get_value
    stored = await get_value(pool, "release_policy")
    value = stored["value"] if stored else None
    value = value or {}
    return {
        "require_package_assets": bool(value.get("require_package_assets", True)),
        "require_playback_review": bool(value.get("require_playback_review", True)),
    }


def describe(problems: list[dict]) -> str:
    """One-line, operator-readable summary for an HTTP error body."""
    return "; ".join(f"{p['code']}: {p['detail']}" for p in problems) or "no problems"
