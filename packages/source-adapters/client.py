"""Rate-limited HTTP fetch shared by all collector adapters.

Best practice (master plan §7): rate-limit, respect robots/terms, log failures.
One client instance is reused across adapters; a small per-host minimum interval
is enforced so polite collection is the default, not an afterthought.
"""

import time
from typing import Optional

import httpx

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
        self._last_hit: dict[str, float] = {}

    def fetch(
        self,
        url: str,
        *,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        host = httpx.URL(url).host
        wait = 0.0
        last = self._last_hit.get(host)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
        if wait:
            time.sleep(wait)

        resp = self._client.get(url, headers=headers, params=params)
        self._last_hit[host] = time.monotonic()
        resp.raise_for_status()
        return resp

    def close(self) -> None:
        self._client.close()
