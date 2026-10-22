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


def reset_reviewer_cache() -> None:
    _REVIEWER_CACHE.clear()


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
        if _is_system_actor(candidate):
            return candidate
        if require:
            raise HTTPException(
                status_code=403,
                detail=(
                    "this action requires a human reviewer credential; service, "
                    "worker and extension credentials cannot approve or attest "
                    "on a person's behalf"
                ),
            )
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

        header = request.headers.get("authorization", "")
        scheme, _, credential = header.partition(" ")
        if scheme.lower() != "bearer" or not credential:
            return _auth_required("missing or malformed Authorization header")

        # constant-time compare for every configured non-human credential
        import hmac

        for configured, cls in self._tokens.items():
            if hmac.compare_digest(credential, configured):
                request.state.actor = None
                request.state.credential_class = cls
                return await call_next(request)

        if self._db_url:
            try:
                reviewer = await self._resolve_reviewer(credential)
            except _BackendUnavailable:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "auth backend unavailable — token validity unknown"},
                )
            if reviewer:
                request.state.actor = reviewer
                request.state.credential_class = CREDENTIAL_REVIEWER
                return await call_next(request)

        return _auth_required("invalid token")

    async def _resolve_reviewer(self, credential: str) -> str | None:
        """sha256 lookup in reviewers (cached 60s for positives only —
        revocation therefore takes effect on the next request or ≤60s)."""
        import asyncpg  # lazy: the hardening module stays importable without DB deps

        th = token_hash(credential)
        hit = _REVIEWER_CACHE.get(th)
        if hit and time.monotonic() - hit[1] < REVIEWER_CACHE_TTL_S:
            return hit[0]
        try:
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
            _REVIEWER_CACHE[th] = (name, time.monotonic())
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
        return response
