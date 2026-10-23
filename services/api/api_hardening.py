"""API hardening: optional bearer-token auth + request logging (v0.13/v0.16).

Auth model: when MTK_API_TOKEN is set, every route except /health requires
`Authorization: Bearer <token>`. When unset (local dev), the API is open —
this matches the runbook's local-development path while closing the exposed
deployment gap.

Credential classes (v0.31):
- MTK_API_TOKEN — service credential for the dashboard server and trusted
  control-plane reads. It carries NO human identity.
- MTK_WORKER_TOKEN — optional worker credential. When absent, workers use the
  service token and are treated as a service principal.
- MTK_EXTENSION_TOKEN — optional browser-extension credential.
- personal reviewer tokens (reviewers table, sha256-hashed at rest, minted
  with services/api/scripts/mint_reviewer.py) — carry the owner's identity:
  request.state.actor is set and routers bind audit/reviewer fields to it.
  This is what lets the dashboard authenticate WITHOUT the master token in
  the browser. Revocation (active=false) is instant; positive lookups are
  cached for 60s.

A service/worker/extension credential may only name an `automation:<stage>`
or `system:` actor. It can never supply a human reviewer name for an approval,
ToS review, redaction review or correction. That separation is what prevents a
compromised worker from appearing as a human approver in audit_log. During
local dev-open mode (no configured token) the old body fallback remains, since
there is no credential boundary to protect; production always configures a
token.

Read identity: GET /whoami → {actor, auth}. Bad reviewer token → 401, same
as any other unauthorized call.

The middleware lives in its own module and is wired via register(app) so it
can be exercised by tests without a database or the real app startup.
"""

import hashlib
import logging
import os
import threading
import time
from typing import Optional

from fastapi import APIRouter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("mtk.api")

OPEN_PATHS = frozenset({"/health"})
TOKEN_ENV = "MTK_API_TOKEN"
WORKER_TOKEN_ENV = "MTK_WORKER_TOKEN"
EXTENSION_TOKEN_ENV = "MTK_EXTENSION_TOKEN"
REVIEWER_CACHE_TTL_S = 60.0

# Credential classes stored on request.state.credential_class.
CREDENTIAL_DISABLED = "disabled"
CREDENTIAL_REVIEWER = "reviewer"
CREDENTIAL_SERVICE = "service"
CREDENTIAL_WORKER = "worker"
CREDENTIAL_EXTENSION = "extension"
SYSTEM_CLASSES = frozenset({CREDENTIAL_SERVICE, CREDENTIAL_WORKER, CREDENTIAL_EXTENSION})
_AUTOMATION_PREFIXES = ("automation:", "system:")

# token_hash -> (name, cached_at). Positives only; revocation takes effect on
# the next request or ≤TTL. reset_reviewer_cache() clears it immediately.
_REVIEWER_CACHE: dict[str, tuple[str, float]] = {}
#: Short negative cache ("token unknown") so invalid tokens cannot force a
#: fresh DB connection per request. Kept deliberately short: a newly created
#: reviewer token starts working within this window at the latest.
REVIEWER_MISS_TTL_S = 5.0
_REVIEWER_MISS_CACHE: dict[str, float] = {}

# ---- brute-force protection (v0.33) -----------------------------------------
# Every 401/503 from the auth gate counts against the client IP in a sliding
# window. Past AUTH_FAILURE_LIMIT failures inside AUTH_FAILURE_WINDOW_S, the
# IP is served 429 for a cooldown — otherwise a reviewer-token could be
# brute-forced at line rate. Only auth-gate outcomes count: a valid credential
# resets the record immediately, and dev-open mode (no tokens) never engages.
AUTH_FAILURE_LIMIT = int(os.environ.get("MTK_AUTH_FAILURE_LIMIT", "15"))
AUTH_FAILURE_WINDOW_S = float(os.environ.get("MTK_AUTH_FAILURE_WINDOW_S", "60"))
_AUTH_FAILURES: dict[str, list[float]] = {}
_AUTH_FAILURES_LOCK = threading.Lock()
_AUTH_FAILURES_MAX_KEYS = 10_000  # bounded: a spoofed-IP flood cannot grow it forever


def _client_ip(request: Request) -> str:
    # Direct peer by default. Trust the proxy chain only when the operator
    # says this deployment sits behind one (MTK_TRUST_PROXY=1) — otherwise the
    # header is client-controlled and trivially spoofable.
    if os.environ.get("MTK_TRUST_PROXY", "").strip().lower() in {"1", "true", "yes"}:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:120]
    return (request.client.host if request.client else "unknown")[:120]


def _auth_failure_check(ip: str, now: float | None = None) -> bool:
    """True when this IP is over the failure budget (a 429 should be served)."""
    now = now if now is not None else time.monotonic()
    with _AUTH_FAILURES_LOCK:
        hits = [t for t in _AUTH_FAILURES.get(ip, ()) if now - t < AUTH_FAILURE_WINDOW_S]
        if len(hits) >= AUTH_FAILURE_LIMIT:
            _AUTH_FAILURES[ip] = hits
            return True
        return False


def _auth_failure_record(ip: str, now: float | None = None) -> None:
    now = now if now is not None else time.monotonic()
    with _AUTH_FAILURES_LOCK:
        hits = [t for t in _AUTH_FAILURES.get(ip, ()) if now - t < AUTH_FAILURE_WINDOW_S]
        hits.append(now)
        if len(_AUTH_FAILURES) < _AUTH_FAILURES_MAX_KEYS or ip in _AUTH_FAILURES:
            _AUTH_FAILURES[ip] = hits
        # dict full and IP unseen: drop the oldest entry instead of growing forever
        elif _AUTH_FAILURES:
            oldest = min(_AUTH_FAILURES, key=lambda k: _AUTH_FAILURES[k][0])
            del _AUTH_FAILURES[oldest]
            _AUTH_FAILURES[ip] = hits


def _auth_failure_reset(ip: str) -> None:
    with _AUTH_FAILURES_LOCK:
        _AUTH_FAILURES.pop(ip, None)


def reset_auth_failures() -> None:
    """Test/ops hook: clear the failure budget (e.g. between scenarios)."""
    with _AUTH_FAILURES_LOCK:
        _AUTH_FAILURES.clear()


# ---- Prometheus-style request counters (v0.33) -------------------------------
# method + route template + status-class → count. Route templates (not raw
# paths) keep cardinality bounded: /schedules/{schedule_id}, never per-entity.
_REQUEST_COUNTS: dict[tuple[str, str, str], int] = {}
_REQUEST_COUNTS_LOCK = threading.Lock()
_REQUEST_COUNTS_MAX_KEYS = 500


def record_request(method: str, route_template: str, status: int) -> None:
    status_class = f"{status // 100}xx"
    try:
        key = (method[:8], route_template[:120], status_class)
    except Exception:  # noqa: BLE001 — observability must never break a request
        return
    with _REQUEST_COUNTS_LOCK:
        if key not in _REQUEST_COUNTS and len(_REQUEST_COUNTS) >= _REQUEST_COUNTS_MAX_KEYS:
            return  # bounded: drop rather than grow unbounded
        _REQUEST_COUNTS[key] = _REQUEST_COUNTS.get(key, 0) + 1


def request_counter_snapshot() -> dict[tuple[str, str, str], int]:
    with _REQUEST_COUNTS_LOCK:
        return dict(_REQUEST_COUNTS)


def auth_failure_ips() -> int:
    """How many client IPs are currently carrying auth-failure history."""
    with _AUTH_FAILURES_LOCK:
        return len(_AUTH_FAILURES)


def reset_reviewer_cache() -> None:
    _REVIEWER_CACHE.clear()
    _REVIEWER_MISS_CACHE.clear()


def token_from_env() -> str | None:
    token = os.environ.get(TOKEN_ENV, "").strip()
    return token or None


def token_hash(token: str) -> str:
    """Reviewers store sha256(token) — high-entropy random tokens, so a plain
    hash is the industry-standard at-rest form (same model as GitHub PATs)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def actor_of(request: Request) -> str | None:
    """Authenticated reviewer identity for THIS request (None = service,
    worker, extension, or unauthenticated dev mode)."""
    return getattr(request.state, "actor", None)


def _auth_pool():
    """The shared db pool, if it is initialized (None during startup)."""
    try:
        import db as _db
    except ImportError:  # pragma: no cover — hardening usable without services
        return None
    getter = getattr(_db, "pool", None) or getattr(_db, "get", None)
    try:
        return getter() if getter else None
    except Exception:  # noqa: BLE001 — never let pool probing break auth
        return None


def credential_class(request: Request) -> str:
    """Which credential authenticated this request (fail closed to service)."""
    return getattr(request.state, "credential_class", CREDENTIAL_SERVICE)


def _is_system_actor(value: Optional[str]) -> bool:
    return bool(value) and str(value).strip().lower().startswith(_AUTOMATION_PREFIXES)


def effective_reviewer(
    request: Request, supplied: Optional[str], *, default: Optional[str] = None,
    require: bool = False,
) -> Optional[str]:
    """The reviewer actually on record for this request.

    - A personal reviewer token binds its owner, overriding every body field.
    - A service/worker/extension credential may only claim an explicit
      automation/system actor. It cannot name a human for `require=True`
      actions, and its human-looking body fields are ignored everywhere else.
    - In dev-open mode (no token configured) the legacy body fallback remains.
    """
    from fastapi import HTTPException

    who = actor_of(request)
    if who:
        return who

    cls = credential_class(request)
    candidate = (supplied or "").strip()

    if cls == CREDENTIAL_DISABLED:
        who = candidate or default
        if require and not who:
            raise HTTPException(
                status_code=403,
                detail="this action requires a recorded reviewer; pass reviewer= explicitly",
            )
        return who

    if cls in SYSTEM_CLASSES:
        # `require=True` is a HUMAN-ONLY gate. An automation/system actor is
        # still a machine credential, so it must not satisfy redaction,
        # correction, ToS or policy attestations. Routes that intentionally
        # accept automation call with require=False and authorize the stage
        # explicitly.
        if require:
            raise HTTPException(
                status_code=403,
                detail=(
                    "this action requires a human reviewer credential; service, "
                    "worker, extension and automation identities cannot approve "
                    "or attest on a person's behalf"
                ),
            )
        if _is_system_actor(candidate):
            return candidate
        return default

    # Unknown class: never let it satisfy a human-only gate.
    if require:
        raise HTTPException(status_code=403, detail="unsupported credential class")
    return default


def service_tokens(token: str | None = None) -> dict[str, str]:
    """Configured non-human credentials, mapped to their class.

    An explicit `token` (tests, embedded app) overrides only the service env.
    Worker/extension env vars are additive; an unset worker token means workers
    fall back to the service token and remain non-human.
    """
    out: dict[str, str] = {}
    service = (token if token is not None else token_from_env() or "").strip()
    if service:
        out[service] = CREDENTIAL_SERVICE
    worker = os.environ.get(WORKER_TOKEN_ENV, "").strip()
    if worker:
        out.setdefault(worker, CREDENTIAL_WORKER)
    extension = os.environ.get(EXTENSION_TOKEN_ENV, "").strip()
    if extension:
        out.setdefault(extension, CREDENTIAL_EXTENSION)
    return out


def register(app, token: str | None = None, db_url: str | None = None) -> None:
    """Attach auth + request-logging middleware. `token` overrides the service
    env; `db_url` enables personal reviewer-token resolution."""
    tokens = service_tokens(token)
    app.add_middleware(_TokenAuthMiddleware, tokens=tokens, db_url=db_url)
    # logging added last → outermost, so auth rejections are logged too
    app.add_middleware(_RequestLogMiddleware)


router = APIRouter(tags=["meta"])


@router.get("/whoami")
async def whoami(request: Request) -> dict:
    """Identity probe: what does THIS credential authenticate as? Requires a
    valid token when auth is enabled — doubles as a liveness check for
    pasted reviewer tokens from the dashboard."""
    actor = actor_of(request)
    auth = credential_class(request)
    return {"actor": actor, "auth": auth}


class _TokenAuthMiddleware(BaseHTTPMiddleware):
    """Bearer-token gate. 401 without/with bad credentials, 503 misconfigured."""

    def __init__(self, app, tokens: dict[str, str], db_url: str | None = None):  # noqa: ANN001
        super().__init__(app)
        self._tokens = dict(tokens)
        self._db_url = db_url

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        if not self._tokens:
            # dev-open mode: no auth, no identity binding
            request.state.actor = None
            request.state.credential_class = CREDENTIAL_DISABLED
            return await call_next(request)
        if request.url.path in OPEN_PATHS:
            request.state.credential_class = CREDENTIAL_DISABLED
            return await call_next(request)

        ip = _client_ip(request)
        if _auth_failure_check(ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "too many failed authentication attempts — "
                                   f"retry after {int(AUTH_FAILURE_WINDOW_S)}s"},
                headers={"Retry-After": str(int(AUTH_FAILURE_WINDOW_S))},
            )

        header = request.headers.get("authorization", "")
        scheme, _, credential = header.partition(" ")
        if scheme.lower() != "bearer" or not credential:
            _auth_failure_record(ip)
            return _auth_required("missing or malformed Authorization header")

        # constant-time compare for every configured non-human credential
        import hmac

        for configured, cls in self._tokens.items():
            if hmac.compare_digest(credential, configured):
                _auth_failure_reset(ip)
                request.state.actor = None
                request.state.credential_class = cls
                return await call_next(request)

        if self._db_url:
            try:
                reviewer = await self._resolve_reviewer(credential)
            except _BackendUnavailable:
                _auth_failure_record(ip)
                return JSONResponse(
                    status_code=503,
                    content={"detail": "auth backend unavailable — token validity unknown"},
                )
            if reviewer:
                _auth_failure_reset(ip)
                request.state.actor = reviewer
                request.state.credential_class = CREDENTIAL_REVIEWER
                return await call_next(request)

        _auth_failure_record(ip)
        return _auth_required("invalid token")

    async def _resolve_reviewer(self, credential: str) -> str | None:
        """sha256 lookup in reviewers (cached 60s; revocation therefore takes
        effect on the next request or ≤60s). Unknown tokens are cached
        negatively for a short window too: every request bearing an invalid
        token used to open a FRESH postgres connection, bypassing the shared
        pool — a cheap per-request connection-amplification vector."""
        import asyncpg  # lazy: the hardening module stays importable without DB deps

        th = token_hash(credential)
        now = time.monotonic()
        hit = _REVIEWER_CACHE.get(th)
        if hit and now - hit[1] < REVIEWER_CACHE_TTL_S:
            return hit[0] or None
        miss = _REVIEWER_MISS_CACHE.get(th)
        if miss and now - miss < REVIEWER_MISS_TTL_S:
            return None
        try:
            pool = _auth_pool()
            if pool is not None:
                name = await pool.fetchval(
                    "SELECT name FROM reviewers WHERE token_hash = $1 AND active", th,
                )
            else:
                # Startup edge: no shared pool yet — one-off connection as before.
                conn = await asyncpg.connect(self._db_url, timeout=5)
                try:
                    name = await conn.fetchval(
                        "SELECT name FROM reviewers WHERE token_hash = $1 AND active", th,
                    )
                finally:
                    await conn.close()
        except Exception:  # noqa: BLE001 — fail closed on any auth-backend error
            logger.exception("auth backend unavailable — failing closed")
            raise _BackendUnavailable() from None
        if name:
            _REVIEWER_CACHE[th] = (name, now)
        else:
            _REVIEWER_MISS_CACHE[th] = now
        return name


class _BackendUnavailable(Exception):
    """The reviewer-token lookup could not reach the database."""


def _auth_required(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


class _RequestLogMiddleware(BaseHTTPMiddleware):
    """One structured line per request: method, path, status, duration."""

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed method=%s path=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                (time.perf_counter() - start) * 1000,
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        # Route TEMPLATE (set by the router after routing) keeps label
        # cardinality bounded; unmatched/404 requests fall back to the raw path
        # but only unmatched literal requests (no interleaved entity ids) can
        # accumulate — the snapshot caps at 500 keys regardless.
        route = request.scope.get("route")
        template = getattr(route, "path", None) or request.url.path
        record_request(request.method, template, response.status_code)
        return response
