"""API hardening: optional bearer-token auth + request logging (v0.13).

Auth model: when MTK_API_TOKEN is set, every route except /health requires
`Authorization: Bearer <token>`. When unset (local dev), the API is open —
this matches the runbook's local-development path while closing the exposed
deployment gap. Workers, the dashboard server components, and the extension
send the same token; a shared secret is intentional at this scale (single
operator, TLS-terminated front door).

The middleware lives in its own module and is wired via register(app) so it
can be exercised by tests without a database or the real app startup.
"""

import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("mtk.api")

OPEN_PATHS = frozenset({"/health"})
TOKEN_ENV = "MTK_API_TOKEN"


def token_from_env() -> str | None:
    token = os.environ.get(TOKEN_ENV, "").strip()
    return token or None


def register(app, token: str | None = None) -> None:
    """Attach auth + request-logging middleware. `token` overrides the env."""

    app.add_middleware(
        _TokenAuthMiddleware,
        token=token if token is not None else token_from_env(),
    )
    # logging added last → outermost, so auth rejections are logged too
    app.add_middleware(_RequestLogMiddleware)


class _TokenAuthMiddleware(BaseHTTPMiddleware):
    """Bearer-token gate. 401 without/with bad credentials, 503 misconfigured."""

    def __init__(self, app, token: str | None):  # noqa: ANN001
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        if self._token is None or request.url.path in OPEN_PATHS:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        scheme, _, credential = header.partition(" ")
        if scheme.lower() != "bearer" or not credential:
            return _auth_required("missing or malformed Authorization header")
        # constant-time compare — the token is a secret
        import hmac

        if not hmac.compare_digest(credential, self._token):
            return _auth_required("invalid token")
        return await call_next(request)


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
