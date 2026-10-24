"""Rate-limited HTTP fetch shared by all collector adapters.

Best practice (master plan §7): rate-limit, respect robots/terms, log failures.
One client instance is reused across adapters; a small per-host minimum interval
is enforced so polite collection is the default, not an afterthought.

Verification fetches go through :meth:`Fetcher.safe_fetch` instead of
``fetch``: that path applies the egress policy (HTTPS-only, public addresses,
validated redirects, bounded body). It uses a separate non-redirecting client
so every hop is checked by :mod:`source_adapters.egress`.
"""

import time
from typing import Optional

import httpx

from .egress import EgressPolicy, FetchResult, safe_fetch

USER_AGENT = "MTKRadarCollector/0.2 (+https://github.com/Kaashmalik/mtk-radar)"
DEFAULT_MIN_INTERVAL = 2.0  # seconds between requests to the same host


class Fetcher:
    def __init__(self, min_interval: float = DEFAULT_MIN_INTERVAL, timeout: float = 20.0):
        self._min_interval = min_interval
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=timeout,
            follow_redirects=True,
        )
        # Verification must validate each redirect hop itself, so it needs a
        # client that never follows automatically. Ambient proxies are ignored
        # (they would bypass address pinning) and keep-alive is disabled
        # because pooled connections are keyed by the pinned IP.
        self._safe_client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=0, max_connections=10),
        )
        self._last_hit: dict[str, float] = {}

    def _throttle(self, url: str) -> None:
        host = httpx.URL(url).host
        wait = 0.0
        last = self._last_hit.get(host)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
        if wait:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def fetch(
        self,
        url: str,
        *,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        self._throttle(url)
        resp = self._client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp

    def safe_fetch(
        self,
        url: str,
        *,
        policy: Optional[EgressPolicy] = None,
        headers: Optional[dict] = None,
        resolver=None,
        clock=None,
    ) -> FetchResult:
        """Verification-grade fetch: bounded, public-only, hop-validated."""
        return safe_fetch(
            url,
            policy=policy or EgressPolicy(),
            headers=headers,
            client=self._safe_client,
            resolver=resolver,
            clock=clock,
            before_request=self._throttle,
        )

    def fetch_policy(
        self,
        url: str,
        *,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        policy: Optional[EgressPolicy] = None,
    ) -> httpx.Response:
        """Policy-bound fetch for collectors.

        Every hop passes the egress policy (HTTPS, public addresses, bounded
        body, pinned connection) and is reconstructed as an httpx.Response, so
        existing collection code (``.content``, ``.json()``) keeps working. A
        non-2xx final status raises, mirroring :meth:`fetch`.
        """
        result = safe_fetch(
            url,
            policy=policy or EgressPolicy(),
            headers=headers,
            params=params,
            client=self._safe_client,
            before_request=self._throttle,
        )
        request = httpx.Request("GET", result.final_url, headers=headers or {})
        response = httpx.Response(
            result.status,
            headers=list(result.headers) if result.headers
            else {"content-type": result.content_type},
            content=result.body,
            request=request,
        )
        response.raise_for_status()
        return response

    def close(self) -> None:
        self._client.close()
        self._safe_client.close()
