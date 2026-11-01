"""MTK RADAR AI — API service (FastAPI).

Single source of truth backend for offers, evidence, projects, and schedules.
Workers and the extension communicate with this API only.

Run locally:
    uvicorn main:app --reload --port 8000
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

import db
import api_hardening
from pagination import (
    decode_cursor,
    decode_datetime,
    decode_uuid,
    encode_cursor,
    set_next_cursor,
)
from attention_api import router as attention_router
from automation_api import router as automation_router
from costs_api import router as costs_router
from captures_api import router as captures_router
import health_api
from health_api import router as health_router
from jobs_api import router as jobs_router
from locks_api import router as locks_router
from media_api import router as media_router
from metrics_api import router as metrics_router
from jsonb import decode_mapping
import tos_review
from normalize import canonicalize_url, hash_parts
from trend_engine import measurement_from_extra, story_key
from offers_api import router as offers_router
from platforms_api import router as platforms_router
from analytics_api import router as analytics_router
from content_studio_api import router as studio_router
from renders_api import router as renders_router
from schedules_api import router as schedules_router
from settings_api import router as settings_router
from trends_api import router as trends_router
from queue_api import router as queue_router
from quota_api import router as quota_router
from storyboard_api import router as storyboard_router
from research_api import router as research_router
from worker_health import router as workers_router
from upload_sessions_api import router as upload_sessions_router
from schemas import ItemIn, PollResult, SourceIn, TosReviewIn
from schemas import MAX_ITEM_CONTEXT_CHARS

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip() or None

#: The pre-hardening local default, kept ONLY as the dev/test fallback
#: (review P2-3): with MTK_ALLOW_UNAUTHENTICATED=1 the sealed local dev/test
#: environment keeps working without DATABASE_URL, while a deployment must
#: set a real URL and never gets a silent hardcoded local postgres DSN.
_DEV_DATABASE_URL = "postgresql://mtk:mtk@localhost:5432/mtk_radar"


def required_database_url() -> str:
    """The DSN the pool must use — fail fast at startup (review P2-3).

    A deployment without DATABASE_URL refuses to boot instead of quietly
    connecting to a hardcoded localhost postgres. The historical dev default
    survives only under the explicit dev-open opt-in, matching the startup
    authentication guard.
    """
    if DATABASE_URL:
        return DATABASE_URL
    if api_hardening.allow_unauthenticated():
        return _DEV_DATABASE_URL
    raise RuntimeError(
        "DATABASE_URL is not configured — the API no longer falls back to a "
        "hardcoded local postgres DSN. Set DATABASE_URL for this deployment "
        f"(or MTK_ALLOW_UNAUTHENTICATED=1 for local development/tests)."
    )

app = FastAPI(title="MTK RADAR AI API", version="0.30.0")
health_api.APP_VERSION = app.version


def _cors_origins() -> list[str]:
    """Browser origins allowed to call the API.

    The dashboard's client-side islands (identity, corrections, settings,
    connections, sources) are same-origin-agnostic: the browser enforces
    CORS. A hardcoded localhost list would break every real deployment
    (127.0.0.1, a domain, a reverse proxy), so the allowlist is
    configurable and seeded from the public base URL.
    """
    raw = os.environ.get("MTK_CORS_ORIGINS", "").strip()
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    public = os.environ.get("MTK_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public and public not in origins:
        origins.append(public)
    if not origins:
        # Dev fallback ONLY: an unconfigured deployment still needs the local
        # dashboard. Once any origin is configured, localhost is NOT silently
        # trusted alongside it — with allow_credentials=True a leftover dev
        # origin on a deployed host is a real exposure.
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    # Explicit, not wildcards (review P2-1): preflights only ever pass what
    # the real clients send. The dashboard calls go through its same-origin
    # /api/backend proxy (Authorization, Content-Type), the extension sends
    # Authorization + Content-Type (apps/extension/core.js), and the dash-
    # board's verbs are GET/HEAD/POST/PUT/PATCH/DELETE (settings PUT,
    # tos-review DELETE, items PATCH, everything else GET/POST).
    allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    # Cursor pagination is unusable from a browser without this: the
    # dashboard cannot read a header the cross-origin allowlist hides.
    expose_headers=["X-Next-Cursor"],
)


# ------------------------------------ request hardening (review P2-1/P2-2)

#: Request bodies are JSON from the dashboard/extension/workers — a 5 MB cap
#: sits far above every real payload and far below anything that could
#: pressure the process. Env-tunable because signed screenshot blobs are the
#: one payload family that can legitimately grow chunk by chunk.
MAX_BODY_BYTES = int(os.environ.get("MTK_API_MAX_BODY_BYTES", "5000000"))

#: Per-credential budget (requests per 60 s). One legitimate client
#: (dashboard proxy, worker, extension) is far under it; a runaway loop is
#: not. Keyed by the sha256 of the presented bearer credential, so tokens
#: never appear in process state in plain form.
RATE_LIMIT_RPM = int(os.environ.get("MTK_API_RATE_LIMIT_RPM", "3000"))
RATE_WINDOW_S = 60


class _RequestHardeningMiddleware:
    """Pure-ASGI request hardening: body-size cap + per-credential budget.

    (a) Content-Length above MAX_BODY_BYTES is refused with 413 before the
        body is read. Bodies without Content-Length (chunked/streaming) can't
        be pre-checked, so their receive channel is BOUNDED: once the cap is
        passed the stream is disconnected — the request fails loudly (never
        a silent truncation that would corrupt a "complete-looking" body).
    (b) Requests are counted per credential token hash in a sliding 60 s
        window (the same in-memory pattern as api_hardening's auth-failure
        budget); over the limit the credential gets 429 + Retry-After.
        Anonymous requests carry no budget key and stay under the auth gate's
        own throttle — and the budget is DISABLED in dev-open mode (no
        credentials configured) so tests are unaffected.

    Wired in app.add_middleware below; direct class instantiation keeps it
    testable without the real app.
    """

    def __init__(self, app, *, enforce_budget: bool,
                 max_body_bytes: int = MAX_BODY_BYTES,
                 requests_per_minute: int = RATE_LIMIT_RPM):  # noqa: ANN001
        self.app = app
        # Body cap ALWAYS applies (it protects the process); only the
        # credential budget is a dev-open opt-out.
        self.max_body_bytes = max(0, int(max_body_bytes))
        self.rpm = max(0, int(requests_per_minute))
        self.enforce_budget = enforce_budget
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        # Bounded: a flood of distinct forged credentials cannot grow the
        # state unboundedly (same discipline as api_hardening).
        self._max_keys = 10_000

    # ---- (b) budget bookkeeping, sliding window --------------------------
    def _budget_key(self, scope) -> str | None:  # noqa: ANN001
        """sha256 of the presented bearer credential; None when absent/other
        scheme (those requests are the auth gate's problem, not a budget)."""
        for name, value in scope.get("headers") or ():
            if name != b"authorization":
                continue
            scheme, _, credential = value.partition(b" ")
            if scheme.lower() != b"bearer" or not credential:
                return None
            return api_hardening.token_hash(credential.decode("latin-1"))
        return None

    def _over_budget_and_record(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, ())
                    if now - t < RATE_WINDOW_S]
            if len(hits) >= self.rpm:
                self._hits[key] = hits
                return True
            hits.append(now)
            if len(self._hits) < self._max_keys or key in self._hits:
                self._hits[key] = hits
            elif self._hits:  # dict full, unseen key: drop the oldest
                oldest = min(self._hits, key=lambda k: self._hits[k][0])
                del self._hits[oldest]
                self._hits[key] = hits
            return False

    # ---- helpers ---------------------------------------------------------
    @staticmethod
    async def _reject(send, status: int, message: str,  # noqa: ANN001
                      extra_headers: tuple[tuple[bytes, bytes], ...] = ()) -> None:
        body = json.dumps({"detail": message}).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        *extra_headers,
                    ]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # (a) declared Content-Length is checkable BEFORE reading anything.
        declared = None
        for name, value in scope.get("headers") or ():
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = None
                break
        if declared is not None and declared > self.max_body_bytes:
            await self._reject(send, 413, "request body too large")
            return

        # (b) per-credential budget (auth-gated deployments only).
        key = self._budget_key(scope)
        if self.enforce_budget and key and self._over_budget_and_record(key):
            await self._reject(
                send, 429,
                "request budget exceeded for this credential — retry after "
                f"{RATE_WINDOW_S}s",
                extra_headers=((b"retry-after",
                                str(RATE_WINDOW_S).encode("ascii")),),
            )
            return

        # (a, streaming) bodies without a checked Content-Length: bound the
        # receive channel. On cap overflow we surface http.disconnect so the
        # consumer never accepts a truncated-but-complete-looking body —
        # "bounded as feasible": Starlette reads raise and the request fails
        # instead of the process buffering unbounded input.
        if declared is None:
            received = 0

            async def bounded_receive():  # noqa: ANN202
                nonlocal received
                message = await receive()
                if message.get("type") == "http.request":
                    received += len(message.get("body") or b"")
                    if received > self.max_body_bytes:
                        return {"type": "http.disconnect"}
                return message

            await self.app(scope, bounded_receive, send)
            return

        await self.app(scope, receive, send)


app.add_middleware(
    _RequestHardeningMiddleware,
    # No credentials configured (dev-open) → no budget keys would ever bind;
    # disabling keeps the test suite's request patterns from any budget.
    enforce_budget=bool(api_hardening.service_tokens()),
)

app.include_router(offers_router)
app.include_router(captures_router)
app.include_router(renders_router)
app.include_router(schedules_router)
app.include_router(settings_router)
app.include_router(automation_router)
app.include_router(costs_router)
app.include_router(health_router)
app.include_router(locks_router)
app.include_router(jobs_router)
app.include_router(platforms_router)
app.include_router(analytics_router)
app.include_router(trends_router)
app.include_router(queue_router)
app.include_router(quota_router)
app.include_router(storyboard_router)
app.include_router(research_router)
app.include_router(studio_router)
app.include_router(attention_router)
app.include_router(workers_router)
app.include_router(upload_sessions_router)
app.include_router(media_router)
app.include_router(metrics_router)

# Optional bearer-token auth (MTK_API_TOKEN, v0.13) + reviewer-token identity
# (v0.16) + structured request logging. Unset token = open local dev; set it
# for anything reachable beyond localhost.
api_hardening.register(app, db_url=DATABASE_URL)
app.include_router(api_hardening.router)


@app.on_event("startup")
async def startup() -> None:
    # Fail-closed boot policy, FIRST (review P0-1/P2-3): refuse to serve
    # unauthenticated, and refuse a missing DATABASE_URL, before the pool or
    # any route is touched. Dev-open (no credentials) needs the EXPLICIT
    # MTK_ALLOW_UNAUTHENTICATED=1 opt-in and logs a CRITICAL banner.
    api_hardening.verify_boot_authentication()
    await db.init(required_database_url())


@app.on_event("shutdown")
async def shutdown() -> None:
    await db.close()


# ---------------------------------------------------------------- health


# ---------------------------------------------------------------- sources


@app.get("/sources")
async def list_sources(
    response: Response,
    enabled: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    cursor: Optional[str] = Query(default=None),
) -> list[dict]:
    pool = db.get()
    parts = decode_cursor(cursor, 3)
    before_tier = parts[0] if parts else None
    before_provider = decode_datetime(parts[1]) if parts else None
    before_id = decode_uuid(parts[2]) if parts else None
    rows = await pool.fetch(
        """
        SELECT id, provider, canonical_domain, account_handle, category, adapter,
               config, enabled, polling_cadence::text AS polling_cadence,
               country_scope, trust_tier::text AS trust_tier, last_checked_at,
               tos_reviewed_at, tos_reviewer, tos_reference
        FROM sources
        WHERE ($1::boolean IS NULL OR enabled = $1)
          AND ($3::text IS NULL
               OR (trust_tier::text, provider, id) < ($3::text, $4::text, $5::uuid))
        ORDER BY trust_tier, provider, id
        LIMIT $2
        """,
        enabled,
        limit,
        before_tier,
        before_provider,
        before_id,
    )
    set_next_cursor(
        response, [dict(r) for r in rows], limit,
        lambda row: encode_cursor(row["trust_tier"], row["provider"], row["id"]),
    )
    # `config` is jsonb — asyncpg hands it over as serialized JSON, so decode
    # it into a real object for API consumers (collectors read config.* keys).
    result = []
    for row in rows:
        source = dict(row)
        source["config"] = decode_mapping(source.get("config"))
        # A review is a statement about terms at a point in time (slice 11).
        source["tos_expires_at"] = tos_review.expires_at(source.get("tos_reviewed_at"))
        source["tos_valid"] = tos_review.is_valid(source.get("tos_reviewed_at"))
        result.append(source)
    return result


@app.get("/source-adapters")
async def list_source_adapters() -> list[dict]:
    """The authoritative adapter registry, in stable UI order.

    The dashboard renders its adapter picker and config fields from this
    endpoint instead of duplicating a hardcoded list (CODE-09). Approval-gated
    adapters are returned with `available: false` and a reason so the form can
    disable them without hiding them from the operator.
    """
    from source_adapters.registry import (
        ADAPTERS,
        APPROVAL_PENDING,
        approval_denial,
    )

    out: list[dict] = []
    for kind, spec in ADAPTERS.items():
        reason = approval_denial(kind)
        out.append({
            "kind": kind,
            "label": spec.label,
            "description": spec.description,
            "collector_polled": spec.collector_polled,
            "config_required": list(spec.config_required),
            "config_optional": list(spec.config_optional),
            "approval_pending": kind in APPROVAL_PENDING,
            "available": reason is None,
            "unavailable_reason": reason,
        })
    return out


@app.post("/sources", status_code=201)
async def create_source(source: SourceIn) -> dict:
    """Register a source. Idempotent on (provider, canonical_domain)."""
    pool = db.get()
    existing = await pool.fetchrow(
        "SELECT id FROM sources WHERE provider = $1 AND COALESCE(canonical_domain, '') = $2",
        source.provider,
        source.canonical_domain or "",
    )
    if existing:
        return {"id": existing["id"], "created": False}

    row = await pool.fetchrow(
        """
        INSERT INTO sources (provider, canonical_domain, account_handle, category,
                             adapter, config, polling_cadence, country_scope, trust_tier, enabled)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::text::interval, $8, $9::trust_tier, $10)
        RETURNING id
        """,
        source.provider,
        source.canonical_domain,
        source.account_handle,
        source.category,
        source.adapter,
        _json(source.config),
        source.polling_cadence,
        source.country_scope,
        source.trust_tier,
        source.enabled,
    )
    # Durable owed-work record: every enabled source owes recurring collection.
    # The collector claims these (v0.33); the list sweep remains the fallback.
    if source.enabled:
        await pool.execute(
            """
            INSERT INTO jobs (kind, entity_id, payload, dedupe_key, max_attempts, run_after)
            VALUES ('collect', $1, $2::jsonb, $3, 5, now())
            ON CONFLICT (dedupe_key) DO NOTHING
            """,
            row["id"],
            _json({"provider": source.provider, "adapter": source.adapter}),
            f"collect:{row['id']}",
        )
    return {"id": row["id"], "created": True}


@app.post("/sources/{source_id}/tos-review")
async def record_tos_review(source_id: uuid.UUID, review: TosReviewIn,
                            request: Request) -> dict:
    """Record a human decision that automated reading of this source is permitted.

    robots.txt is checked separately at fetch time; this is the contractual
    permission. The reviewer is bound from the authenticated token when present,
    otherwise the explicit body field is the recorded identity (service callers).
    Re-recording replaces the previous attestation; the audit log keeps history.
    """
    actor = api_hardening.effective_reviewer(request, review.reviewer, require=True)
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE sources
        SET tos_reviewed_at = clock_timestamp(), tos_reviewer = $2, tos_reference = $3
        WHERE id = $1
        RETURNING id, tos_reviewed_at, tos_reviewer, tos_reference
        """,
        source_id, actor, review.reference,
    )
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, 'sources', $3, $4::jsonb)",
        actor, "tos_review:recorded", source_id,
        _json({"reference": review.reference}),
    )
    return dict(row)


@app.delete("/sources/{source_id}/tos-review")
async def revoke_tos_review(source_id: uuid.UUID, request: Request,
                            reviewer: Optional[str] = Query(default=None)) -> dict:
    """Withdraw the permission to read a source (WP01 slice 11).

    Clearing the record stops new machine-collected evidence immediately; it does
    not rewrite evidence already stored, and reviewer-attested snapshots remain
    possible. The audit log records who withdrew it.
    """
    actor = api_hardening.effective_reviewer(request, reviewer, require=True)
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE sources
        SET tos_reviewed_at = NULL, tos_reviewer = NULL, tos_reference = NULL
        WHERE id = $1
        RETURNING id
        """,
        source_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, 'sources', $3, $4::jsonb)",
        actor, "tos_review:revoked", source_id, _json({}),
    )
    return {"id": row["id"], "revoked": True}


@app.post("/sources/{source_id}/poll-result")
async def poll_result(source_id: uuid.UUID, result: PollResult) -> dict:
    """Collectors report back after each poll → updates last_checked_at and health.

    A healthy poll also RE-ARMS the durable `collect` job with the source's
    cadence (the queue only wakes the collector when the next poll is due);
    a failed poll retries sooner. The cadence sweep stays as the fallback."""
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE sources
        SET last_checked_at = now(),
            config = config || $2::jsonb
        WHERE id = $1
        RETURNING id, enabled,
                  COALESCE(EXTRACT(epoch FROM polling_cadence)::int, 21600) AS cadence_s
        """,
        source_id,
        _json({"health": {"ok": result.ok, "detail": result.detail}}),
    )
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
    if row["enabled"]:
        # Recurring job contract: healthy poll → pending with the source's
        # cadence and a fresh attempt budget; failed poll → pending sooner,
        # keeping the attempt count so 5 consecutive failures dead-letter the
        # job into operator attention. The success path also clears any stale
        # claim lease, so a worker lost mid-poll cannot wedge the source.
        delay_s = row["cadence_s"] if result.ok else 300
        await pool.execute(
            """
            INSERT INTO jobs (kind, entity_id, payload, dedupe_key, max_attempts, run_after)
            VALUES ('collect', $1, '{}'::jsonb, $2, 5, now() + make_interval(secs => $3::int))
            ON CONFLICT (dedupe_key) DO UPDATE
            SET status = CASE
                    WHEN $4 THEN 'pending'
                    WHEN jobs.attempts >= 5 THEN 'dead'
                    ELSE 'pending' END,
                run_after = now() + make_interval(secs => $3::int),
                attempts = CASE WHEN $4 THEN 0 ELSE jobs.attempts END,
                last_error = $5,
                lease_holder = NULL, lease_expires_at = NULL, updated_at = now()
            """,
            source_id, f"collect:{source_id}", delay_s, result.ok,
            (result.detail or None),
        )
    return {"id": row["id"], "last_checked_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------- items (inbox)


@app.post("/items", status_code=201)
async def create_item(item: ItemIn) -> dict:
    """Ingest a candidate from a collector or the extension.

    Dedup guarantees (master plan §18 week 2): a candidate appears EXACTLY ONCE
    — keyed by (source_id, external_item_id) and by the canonical URL + text hash.
    Re-submissions return the existing item with `created: false, duplicate: true`.
    """
    pool = db.get()
    # EP-04: provenance must record WHERE the candidate came from — resolve
    # (extension saves omit source_id) can never contaminate this flag.
    from_extension = item.source_id is None
    resolved = await _resolve_source_id(pool, item.source_id)
    if item.source_id is None:
        item.source_id = resolved
    source_id = item.source_id

    external_item_id = item.external_item_id or str(uuid.uuid4())
    try:
        canonical = canonicalize_url(str(item.url))
    except ValueError as exc:
        # a malformed port (e.g. https://host:abc/) raised out of urlsplit —
        # caller input, so a 4xx, never a 500
        raise HTTPException(status_code=422,
                            detail=f"unparseable item url: {exc}") from exc
    dupe_group = canonical
    text_hash = hash_parts(canonical, item.title, item.selection or item.text)
    story = story_key(item.title)

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO items (source_id, external_item_id, url, canonical_url, title,
                                   observed_at, published_at, text_hash, duplicate_group,
                                   story_key, text, selection, account_handle, extra)
                VALUES ($1, $2, $3, $4, $5,
                        COALESCE($6, now()), $7, $8, $9, $10, $11, $12, $13, $14::jsonb)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                source_id,
                external_item_id,
                str(item.url),
                canonical,
                item.title,
                item.observed_at,
                item.published_at,
                text_hash,
                dupe_group,
                story,
                item.text,
                item.selection,
                item.account_handle,
                _json(item.extra or {}),
            )

            # G07: EVERY retrieval also appends a raw typed observation —
            # story dedup (items UNIQUE keys) and measurement history are
            # separate ledgers. Re-observing an unchanged entity records the
            # (identical) measurement again; only DELTAS between rows may
            # ever become momentum (G08), so unchanged fields cannot fake a
            # rising trend.
            adapter = await conn.fetchval(
                "SELECT adapter::text FROM sources WHERE id = $1", source_id)
            measurements = measurement_from_extra(item.extra)
            entity_key = f"{adapter or 'unknown'}:{external_item_id}"
            payload_hash = hash_parts(
                canonical, json.dumps(item.extra or {}, sort_keys=True,
                                      default=str),
                (item.text or "")[:4000],
            )
            await conn.execute(
                """
                INSERT INTO source_observations
                    (source_id, adapter, external_id, entity_key, url,
                     observed_at, measurements, payload_hash, excerpt, provenance)
                VALUES ($1, $2, $3, $4, $5,
                        COALESCE($6, now()), $7::jsonb, $8, $9,
                        $10::jsonb)
                """,
                source_id,
                adapter or "unknown",
                external_item_id,
                entity_key,
                canonical,
                item.observed_at,
                _json(measurements),
                payload_hash,
                (item.text or item.selection or "")[:MAX_ITEM_CONTEXT_CHARS]
                or None,
                _json({
                    "source_kind": (item.extra or {}).get("source_kind"),
                    "intake": "extension" if from_extension else "collector",
                    "context_type": (item.extra or {}).get("context_type"),
                    "context_url": (item.extra or {}).get("context_url"),
                }),
            )

    if row:
        return {"id": row["id"], "created": True, "duplicate": False, "canonical_url": canonical}

    # Conflict → fetch the existing candidate. `ON CONFLICT DO NOTHING` (no
    # target) covers BOTH documented keys: (source_id, external_item_id) and
    # the canonical-URL + text-hash pair enforced by the unique partial index
    # added in migration 031 — a resubmission with a fresh external_item_id no
    # longer creates a second row.
    existing = await pool.fetchrow(
        """
        SELECT id FROM items
        WHERE (source_id = $1 AND external_item_id = $2)
           OR (canonical_url = $3 AND text_hash = $4)
        ORDER BY observed_at
        LIMIT 1
        """,
        source_id,
        external_item_id,
        canonical,
        text_hash,
    )
    return {
        "id": existing["id"] if existing else None,
        "created": False,
        "duplicate": True,
        "canonical_url": canonical,
    }


@app.get("/items")
async def list_items(
    response: Response,
    processed: Optional[bool] = None,
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, le=200),
    cursor: Optional[str] = Query(default=None),
) -> list[dict]:
    """Review inbox — unprocessed candidates first (most recent).

    Paginated with an opaque keyset cursor so the inbox tail is reachable;
    a fixed LIMIT previously hid every item older than the newest page.
    `q` searches title and URL (inbox search/filter, plan §6 P0).
    """
    pool = db.get()
    parts = decode_cursor(cursor, 2)
    before_observed = decode_datetime(parts[0]) if parts else None
    before_id = decode_uuid(parts[1]) if parts else None
    rows = await pool.fetch(
        """
        SELECT i.id, i.url, i.canonical_url, i.title, i.observed_at, i.published_at,
               i.duplicate_group, i.processed,
               s.provider AS source_provider, s.category AS source_category,
               s.trust_tier::text AS trust_tier
        FROM items i
        LEFT JOIN sources s ON s.id = i.source_id
        WHERE ($1::boolean IS NULL OR i.processed = $1)
          AND ($5::text IS NULL OR i.title ILIKE '%' || $5 || '%'
               OR i.url ILIKE '%' || $5 || '%'
               OR coalesce(i.canonical_url, '') ILIKE '%' || $5 || '%')
          AND ($3::timestamptz IS NULL
               OR (i.observed_at, i.id) < ($3::timestamptz, $4::uuid))
        ORDER BY i.observed_at DESC, i.id DESC
        LIMIT $2
        """,
        processed,
        limit,
        before_observed,
        before_id,
        q,
    )
    out = [dict(r) for r in rows]
    set_next_cursor(
        response, out, limit,
        lambda row: encode_cursor(row["observed_at"], row["id"]),
    )
    return out


@app.get("/items/{item_id}")
async def get_item(item_id: uuid.UUID) -> dict:
    """One inbox item by id — the dashboard's `?saved_item=` deep link.

    The extension opens `/inbox?saved_item=<id>` after a save; this endpoint
    makes the link exact instead of hoping the item is on page one.
    """
    pool = db.get()
    row = await pool.fetchrow(
        """
        SELECT i.id, i.url, i.canonical_url, i.title, i.observed_at, i.published_at,
               i.duplicate_group, i.processed,
               s.provider AS source_provider, s.category AS source_category,
               s.trust_tier::text AS trust_tier
        FROM items i
        LEFT JOIN sources s ON s.id = i.source_id
        WHERE i.id = $1
        """,
        item_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="item not found")
    return dict(row)


@app.patch("/items/{item_id}/processed")
async def mark_processed(item_id: uuid.UUID, processed: bool = True) -> dict:
    pool = db.get()
    row = await pool.fetchrow(
        "UPDATE items SET processed = $2 WHERE id = $1 RETURNING id",
        item_id,
        processed,
    )
    if not row:
        raise HTTPException(status_code=404, detail="item not found")
    return {"id": row["id"], "processed": processed}


# ---------------------------------------------------------------- helpers


async def _resolve_source_id(pool: asyncpg.Pool, source_id: Optional[uuid.UUID]) -> uuid.UUID:
    """Collectors pass their registered source. Extension saves resolve to (or
    create) the single 'browser-extension' Tier-B source."""
    if source_id is not None:
        row = await pool.fetchrow("SELECT id FROM sources WHERE id = $1", source_id)
        if not row:
            raise HTTPException(status_code=404, detail="source not found")
        return row["id"]

    row = await pool.fetchrow("SELECT id FROM sources WHERE adapter = 'extension' LIMIT 1")
    if row:
        return row["id"]

    # Only one creation race-winner matters; use advisory lock against races.
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(872341)")
            row = await conn.fetchrow("SELECT id FROM sources WHERE adapter = 'extension' LIMIT 1")
            if row:
                return row["id"]
            row = await conn.fetchrow(
                """
                INSERT INTO sources (provider, category, adapter, trust_tier, polling_cadence)
                VALUES ('Browser extension (saved links)', 'saved_links', 'extension',
                        'B_discovery_lead', '0 seconds')
                RETURNING id
                """
            )
            return row["id"]


def _json(value) -> str:
    import json

    return json.dumps(value, default=str)


# TODO(week-9): POST /schedules — schedule creation requires approved version hash.
