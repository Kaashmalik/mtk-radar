"""Client-side helper for the API's opaque keyset cursors.

Workers must not re-read the same first page forever. `iter_pages` follows the
`X-Next-Cursor` response header until the API reports no further records,
while keeping the caller's original query parameters (state filters etc.).

Import pattern (workers):
    sys.path.insert(0, <repo>/packages)
    from api_paging import iter_pages
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator

CURSOR_HEADER = "X-Next-Cursor"
MAX_PAGES = 10_000


def iter_pages(client, path: str, params: dict[str, Any] | None = None,
               *, limit: int | None = None, max_pages: int = MAX_PAGES
               ) -> Iterator[dict[str, Any]]:
    """Yield every row across pages, following the API's next-page cursor."""
    query = {key: value for key, value in (params or {}).items()
             if value is not None}
    if limit is not None:
        query["limit"] = limit

    cursor: str | None = None
    for _ in range(max_pages):
        if cursor:
            query["cursor"] = cursor
        response = client.get(path, params=query)
        status = int(getattr(response, "status_code", 200) or 200)
        if status >= 400:
            raise ValueError(f"{path} returned HTTP {status}")
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError(f"{path} did not return a list page")
        yield from rows
        headers = getattr(response, "headers", None) or {}
        cursor = headers.get(CURSOR_HEADER)
        if not cursor or not rows:
            return
    raise RuntimeError(f"{path}: exceeded {max_pages} pages — cursor never ended")


def fetch_all(client, path: str, params: dict[str, Any] | None = None,
              *, limit: int | None = None) -> list[dict[str, Any]]:
    return list(iter_pages(client, path, params, limit=limit))


def paged(client, path: str, params: dict[str, Any] | None = None,
          *, limit: int | None = None) -> Iterable[dict[str, Any]]:
    """Alias kept explicit for call sites that prefer a generator name."""
    return iter_pages(client, path, params, limit=limit)


__all__ = ["CURSOR_HEADER", "iter_pages", "fetch_all", "paged"]
