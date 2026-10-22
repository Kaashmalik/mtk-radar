"""Opaque cursor + media range parsing.

These are pure unit checks: they prove malformed input fails closed and that
the cursor round-trips without leaking a query shape to callers.
"""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from media_api import parse_range
from pagination import decode_cursor, decode_datetime, decode_uuid, encode_cursor


def test_cursor_round_trips_sort_keys():
    when = datetime(2026, 10, 22, 12, 30, tzinfo=timezone.utc)
    cursor = encode_cursor(when, "00000000-0000-0000-0000-000000000001")
    parts = decode_cursor(cursor, 2)
    assert parts == [when.isoformat(),
                     "00000000-0000-0000-0000-000000000001"]
    assert decode_datetime(parts[0]) == when
    assert str(decode_uuid(parts[1])) == "00000000-0000-0000-0000-000000000001"


def test_cursor_is_empty_only_when_omitted():
    assert decode_cursor(None, 2) is None
    assert decode_cursor("", 2) is None


@pytest.mark.parametrize("value", ["not-base64!!", "e30", "W10", "WyJvbmUiXQ"])
def test_malformed_cursor_is_a_client_error(value):
    with pytest.raises(HTTPException) as exc:
        decode_cursor(value, 2)
    assert exc.value.status_code == 422


def test_cursor_arity_is_enforced():
    with pytest.raises(HTTPException):
        decode_cursor(encode_cursor("only-one"), 2)


def test_bad_timestamp_and_uuid_are_client_errors():
    with pytest.raises(HTTPException):
        decode_datetime("not-a-time")
    with pytest.raises(HTTPException):
        decode_uuid("not-a-uuid")


class TestByteRange:
    def test_absent_header_means_whole_file(self):
        assert parse_range(None, 1000) is None

    def test_closed_range(self):
        assert parse_range("bytes=0-99", 1000) == (0, 99)

    def test_open_ended_range(self):
        assert parse_range("bytes=500-", 1000) == (500, 999)

    def test_suffix_range(self):
        assert parse_range("bytes=-100", 1000) == (900, 999)

    def test_end_is_clamped(self):
        assert parse_range("bytes=900-5000", 1000) == (900, 999)

    @pytest.mark.parametrize("header", ["bytes=1000-", "bytes=2000-3000", "bytes=-0"])
    def test_unsatisfiable_range_is_416(self, header):
        with pytest.raises(HTTPException) as exc:
            parse_range(header, 1000)
        assert exc.value.status_code == 416
        assert exc.value.headers["Content-Range"] == "bytes */1000"

    @pytest.mark.parametrize("header", ["bytes=abc", "items=0-1", "bytes=1-2-3"])
    def test_unparseable_range_falls_back_to_whole_file(self, header):
        assert parse_range(header, 1000) is None
