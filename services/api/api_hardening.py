"""API hardening: optional bearer-token auth + request logging (v0.13/v0.16).

Auth model: when MTK_API_TOKEN is set, every route except /health requires
`Authorization: Bearer <token>`. When unset (local dev), the API is open —
this matches the runbook's local-development path while closing the exposed
deployment gap.

Two credential classes (v0.16):
- the shared MTK_API_TOKEN — for workers/extension; carries NO identity
  (audit actor falls back to the request body's reviewer field as before)
- personal reviewer tokens (reviewers table, sha256-hashed at rest, minted
  with services/api/scripts/mint_reviewer.py) — carry the owner's identity:
  request.state.actor is set and routers bind audit/reviewer fields to it.
  This is what lets the dashboard authenticate WITHOUT the master token in
  the browser. Revocation (active=false) is instant; positive lookups are
  cached for 60s.

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
REVIEWER_CACHE_TTL_S = 60.0

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
    """Authenticated reviewer identity for THIS request (None = service token,
    unauthenticated dev mode, or a system/writer actor)."""
    return getattr(request.state, "actor", None)


def effective_reviewer(
    request: Request, supplied: Optional[str], *, default: Optional[str] = None,
    require: bool = False,
) -> Optional[str]:
    """The reviewer actually on record: the authenticated reviewer token wins;
    the request-body/query string is the fallback for service-token callers
    and open-dev mode. `require=True` enforces the §3/§17 rule that approval
    actions always name a human."""
    who = actor_of(request) or (supplied or "").strip() or default
    if require and not who:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="this action requires a recorded reviewer (authentication binds "
                   "identity, or pass reviewer= explicitly)",
        )
    return who


def register(app, token: str | None = None, db_url: str | None = None) -> None:
    """Attach auth + request-logging middleware. `token` overrides the env;
    `db_url` enables personal reviewer-token resolution."""
    global _effective_token
    _effective_token = token if token is not None else token_from_env()

    app.add_middleware(
        _TokenAuthMiddleware,
        token=token if token is not None else token_from_env(),
        db_url=db_url,
    )
    # logging added last → outermost, so auth rejections are logged too
    app.add_middleware(_RequestLogMiddleware)


router = APIRouter(tags=["meta"])

_effective_token: Optional[str] = None  # what register() actually configured


@router.get("/whoami")
async def whoami(request: Request) -> dict:
    """Identity probe: what does THIS credential authenticate as? Requires a
    valid token when auth is enabled — doubles as a liveness check for
    pasted reviewer tokens from the dashboard."""
    actor = actor_of(request)
    if actor:
        auth = "reviewer"
    elif _effective_token or token_from_env():
        auth = "service"
    else:
        auth = "disabled"
    return {"actor": actor, "auth": auth}


class _TokenAuthMiddleware(BaseHTTPMiddleware):
    """Bearer-token gate. 401 without/with bad credentials, 503 misconfigured."""

    def __init__(self, app, token: str | None, db_url: str | None = None):  # noqa: ANN001
        super().__init__(app)
        self._token = token
        self._db_url = db_url

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        if self._token is None:
            # dev-open mode: no auth, no identity binding
            request.state.actor = None
            return await call_next(request)
        if request.url.path in OPEN_PATHS:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        scheme, _, credential = header.partition(" ")
        if scheme.lower() != "bearer" or not credential:
            return _auth_required("missing or malformed Authorization header")

        # constant-time compare for the shared secret
        import hmac

        if hmac.compare_digest(credential, self._token):
            request.state.actor = None  # service token → body supplies actors
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
