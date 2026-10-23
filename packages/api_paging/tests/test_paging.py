"""Client cursor following — the worker side of the backlog fix."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # packages/

from api_paging import fetch_all, iter_pages  # noqa: E402


class FakeResponse:
    def __init__(self, rows, cursor=None, status_code=200):
        self._rows = rows
        self.status_code = status_code
        self.headers = {"X-Next-Cursor": cursor} if cursor else {}

    def json(self):
        return self._rows


class FakeClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        return self.pages.pop(0)


def test_follows_every_cursor_page_and_keeps_original_filters():
    client = FakeClient([
        FakeResponse([{"id": 1}], cursor="page-2"),
        FakeResponse([{"id": 2}], cursor="page-3"),
        FakeResponse([{"id": 3}]),
    ])
    rows = fetch_all(client, "/schedules", {"state": "published"}, limit=2)

    assert [row["id"] for row in rows] == [1, 2, 3]
    assert client.calls[0][1] == {"state": "published", "limit": 2}
    assert client.calls[1][1] == {"state": "published", "limit": 2,
                                  "cursor": "page-2"}
    assert client.calls[2][1] == {"state": "published", "limit": 2,
                                  "cursor": "page-3"}


def test_a_broken_page_raises_instead_of_silently_truncating():
    class BrokenClient:
        def get(self, path, params=None):
            return FakeResponse({"detail": "boom"}, status_code=503)

    with pytest.raises(ValueError):
        list(iter_pages(BrokenClient(), "/offers"))


def test_an_endless_cursor_is_bounded():
    pages = [FakeResponse([{"id": index}], cursor=f"c{index}") for index in range(5)]

    class EndlessClient:
        def get(self, path, params=None):
            return pages.pop(0) if pages else FakeResponse([{"id": 99}], cursor="again")

    with pytest.raises(RuntimeError):
        list(iter_pages(EndlessClient(), "/offers", max_pages=3))


def test_an_empty_page_terminates_even_with_a_cursor():
    client = FakeClient([FakeResponse([], cursor="should-not-matter")])
    assert fetch_all(client, "/offers") == []

def test_a_full_page_without_a_cursor_raises_instead_of_truncating():
    """A dropped/missing X-Next-Cursor on a FULL page used to look like the
    end of the collection — silently truncating retries/corrections/sweeps."""
    client = FakeClient([FakeResponse([{"id": 1}, {"id": 2}])])
    with pytest.raises(RuntimeError):
        list(iter_pages(client, "/schedules", {"state": "scheduled"}, limit=2))


def test_a_short_page_without_a_cursor_is_still_the_end():
    client = FakeClient([FakeResponse([{"id": 1}])])
    assert [row["id"] for row in iter_pages(client, "/schedules", limit=5)] == [1]
