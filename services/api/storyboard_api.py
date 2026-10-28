"""Storyboard editor + public-page capture requests (2026-10-28 plan).

  GET  /offers/{id}/storyboard             current version + suggestion + inputs
  POST /offers/{id}/storyboard             save a NEW version (human reviewer)
  GET  /offers/{id}/page-captures          captured public pages for the offer
  POST /offers/{id}/page-captures/request  ask the worker to capture URLs (human)
  POST /page-captures/{id}/result          worker reports one capture outcome

The honesty rules live in packages/storyboard and are applied on save and
again at render time: claim scenes are always derived from the CURRENT
claim ledger (wording, attribution, source), contradicted claims are refused,
and free text is bounded. Saves are versioned with optimistic concurrency
(`expected_version`), so two reviewers cannot silently overwrite each other.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import db
from api_hardening import (
    CREDENTIAL_DISABLED,
    CREDENTIAL_REVIEWER,
    credential_class,
    effective_reviewer,
)
from research_api import latest_brief_with_claims
from settings_store import audit

_PACKAGES = Path(__file__).resolve().parents[2] / "packages"
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

import storyboard  # noqa: E402
from source_adapters.egress import EgressError, EgressPolicy, validate_url  # noqa: E402

router = APIRouter(tags=["storyboard"])

MAX_URLS_PER_REQUEST = 10


def _require_human(request: Request, what: str) -> str:
    if credential_class(request) not in (CREDENTIAL_REVIEWER, CREDENTIAL_DISABLED):
        raise HTTPException(status_code=403, detail=f"{what} is a human action — "
                                                    "use a reviewer credential")
    actor = effective_reviewer(request, None, default="reviewer")
    if not actor or actor.startswith("automation:"):
        raise HTTPException(status_code=403, detail=f"{what} needs a named reviewer")
    return actor


async def _offer_exists(pool, offer_id: uuid.UUID) -> None:
    if not await pool.fetchval("SELECT 1 FROM offers WHERE id = $1", offer_id):
        raise HTTPException(status_code=404, detail="offer not found")


def _capture_row(row) -> dict[str, Any]:
    out = dict(row)
    out["id"] = str(out["id"])
    out["offer_id"] = str(out["offer_id"])
    for key in ("captured_at", "created_at"):
        if out.get(key) is not None:
            out[key] = out[key].isoformat()
    out.pop("image_ref", None)  # storage refs stay server-side
    return out


async def _page_captures(pool, offer_id: uuid.UUID) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT id, offer_id, url, final_url, title, status, detail, image_ref,
               image_sha256, http_status, requested_by, captured_at, created_at
        FROM page_captures WHERE offer_id = $1
        ORDER BY created_at DESC LIMIT 100
        """,
        offer_id,
    )
    return [_capture_row(r) for r in rows]


async def _current_storyboard(pool, offer_id: uuid.UUID) -> Optional[dict]:
    row = await pool.fetchrow(
        """
        SELECT version, scenes::text AS scenes, sha256, brief_id, created_by, created_at
        FROM storyboards WHERE offer_id = $1 ORDER BY version DESC LIMIT 1
        """,
        offer_id,
    )
    if not row:
        return None
    return {"version": row["version"], "scenes": json.loads(row["scenes"]),
            "sha256": row["sha256"],
            "brief_id": str(row["brief_id"]) if row["brief_id"] else None,
            "created_by": row["created_by"], "created_at": row["created_at"].isoformat()}


# ----------------------------------------------------------------- storyboard

@router.get("/offers/{offer_id}/storyboard")
async def get_storyboard(offer_id: uuid.UUID) -> dict:
    pool = db.get()
    offer = await pool.fetchrow("SELECT id, title FROM offers WHERE id = $1", offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    brief = await latest_brief_with_claims(pool, offer_id)
    pages = [p for p in await _page_captures(pool, offer_id) if p["status"] == "ok"]
    current = await _current_storyboard(pool, offer_id)
    problems: list[str] = []
    if current and brief:
        # What the renderer would drop TODAY (e.g. a claim contradicted since).
        _, problems = storyboard.validate(current["scenes"], brief, pages)
    return {
        "brief": ({"id": str(brief["id"]), "version": brief.get("version"),
                   "content_type": brief.get("content_type")} if brief else None),
        "current": current,
        "suggested": storyboard.suggest(dict(offer), brief, pages) if brief else [],
        "claims": [
            {"id": c["id"], "status": c["status"], "claim_class": c["claim_class"],
             "text": c.get("permitted_wording") or c["claim_text"]}
            for c in (brief or {}).get("claims", [])
        ],
        "page_captures": pages,
        "problems": problems,
        "limits": {"max_scenes": storyboard.MAX_SCENES,
                   "weight": [storyboard.MIN_WEIGHT, storyboard.MAX_WEIGHT],
                   "heading": storyboard.MAX_HEADING, "body": storyboard.MAX_BODY},
    }


class StoryboardIn(BaseModel):
    scenes: list[dict] = Field(min_length=1, max_length=storyboard.MAX_SCENES)
    # Optimistic concurrency: the version the editor started from (None = new).
    expected_version: Optional[int] = None


@router.post("/offers/{offer_id}/storyboard", status_code=201)
async def save_storyboard(offer_id: uuid.UUID, body: StoryboardIn, request: Request) -> dict:
    actor = _require_human(request, "editing the storyboard")
    pool = db.get()
    await _offer_exists(pool, offer_id)
    brief = await latest_brief_with_claims(pool, offer_id)
    if not brief or brief.get("content_type") != "explainer":
        raise HTTPException(status_code=409,
                            detail="storyboards apply to research explainers — create an "
                                   "explainer brief first")
    pages = [p for p in await _page_captures(pool, offer_id) if p["status"] == "ok"]
    scenes, problems = storyboard.validate(body.scenes, brief, pages)
    if problems:
        raise HTTPException(status_code=422, detail={"problems": problems})
    digest = storyboard.digest(scenes)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))",
                               f"storyboard:{offer_id}")
            latest = await conn.fetchval(
                "SELECT COALESCE(MAX(version), 0) FROM storyboards WHERE offer_id = $1",
                offer_id)
            if (body.expected_version or 0) != latest:
                raise HTTPException(
                    status_code=409,
                    detail=f"the storyboard changed (now v{latest}) — reload and "
                           "re-apply your edits")
            version = latest + 1
            await conn.execute(
                """
                INSERT INTO storyboards (offer_id, version, scenes, sha256, brief_id, created_by)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6)
                """,
                offer_id, version, json.dumps(scenes), digest,
                uuid.UUID(str(brief["id"])), actor,
            )
    await audit(pool, actor=actor, action="storyboard:save", entity="offers",
                entity_id=offer_id, detail={"version": version, "sha256": digest,
                                            "scenes": len(scenes)})
    return {"version": version, "sha256": digest, "scenes": scenes}


# --------------------------------------------------------------- page capture

class PageCaptureRequestIn(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=MAX_URLS_PER_REQUEST)


@router.get("/offers/{offer_id}/page-captures")
async def list_page_captures(offer_id: uuid.UUID) -> list[dict]:
    pool = db.get()
    await _offer_exists(pool, offer_id)
    return await _page_captures(pool, offer_id)


@router.post("/offers/{offer_id}/page-captures/request", status_code=202)
async def request_page_captures(offer_id: uuid.UUID, body: PageCaptureRequestIn,
                                request: Request) -> dict:
    """Queue public-page screenshots. Each URL is checked against the egress
    policy here (https, no credentials, port 443, no private IP literal); the
    worker re-resolves DNS and refuses non-public addresses before loading."""
    actor = _require_human(request, "requesting page captures")
    pool = db.get()
    await _offer_exists(pool, offer_id)
    policy = EgressPolicy()
    accepted, refused = [], []
    for raw in dict.fromkeys(u.strip() for u in body.urls):
        try:
            validate_url(raw, policy)
        except EgressError as exc:
            refused.append({"url": raw[:300], "detail": str(exc)})
            continue
        accepted.append(raw)
    ids: list[str] = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for url in accepted:
                capture_id = await conn.fetchval(
                    "INSERT INTO page_captures (offer_id, url, requested_by) "
                    "VALUES ($1, $2, $3) RETURNING id",
                    offer_id, url[:2000], actor)
                ids.append(str(capture_id))
            if ids:
                await conn.execute(
                    "INSERT INTO jobs (kind, entity_id, payload, max_attempts) "
                    "VALUES ('page_capture', $1, $2::jsonb, 3)",
                    offer_id, json.dumps({"capture_ids": ids}))
    if ids:
        await audit(pool, actor=actor, action="page_capture:request", entity="offers",
                    entity_id=offer_id, detail={"count": len(ids)})
    return {"queued": ids, "refused": refused}


class PageCaptureResultIn(BaseModel):
    status: str = Field(pattern="^(ok|failed|refused)$")
    final_url: Optional[str] = Field(default=None, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=300)
    image_ref: Optional[str] = Field(default=None, max_length=1000)
    image_sha256: Optional[str] = Field(default=None, pattern="^[0-9a-f]{64}$")
    http_status: Optional[int] = None
    detail: Optional[str] = Field(default=None, max_length=1000)


@router.post("/page-captures/{capture_id}/result")
async def page_capture_result(capture_id: uuid.UUID, body: PageCaptureResultIn) -> dict:
    if body.status == "ok" and not (body.image_ref and body.image_sha256):
        raise HTTPException(status_code=422, detail="an ok capture needs image_ref + image_sha256")
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE page_captures
        SET status = $2, final_url = $3, title = $4, image_ref = $5, image_sha256 = $6,
            http_status = $7, detail = $8, captured_at = now()
        WHERE id = $1 AND status = 'requested'
        RETURNING id, status
        """,
        capture_id, body.status, body.final_url, body.title, body.image_ref,
        body.image_sha256, body.http_status, body.detail,
    )
    if not row:
        exists = await pool.fetchval("SELECT status FROM page_captures WHERE id = $1", capture_id)
        if exists is None:
            raise HTTPException(status_code=404, detail="page capture not found")
        raise HTTPException(status_code=409, detail=f"page capture already {exists}")
    return {"id": str(row["id"]), "status": row["status"]}
