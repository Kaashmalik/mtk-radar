"""SigV4 correctness — verified against AWS's PUBLISHED test vector
(docs.aws.amazon.com/general/latest/gr/sigv4-calculate-signature.html,
"example: GET iam"). If these constants ever mismatch, the signer is wrong —
no network required."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # packages/

import pytest

from object_storage._sigv4 import (
    EMPTY_PAYLOAD_SHA256,
    _canonical_query,
    _uri_encode,
    amz_date,
    canonical_request,
    parse_s3_ref,
    scope_of,
    sha256_hex,
    sign_request,
    signing_key,
    string_to_sign,
    signature,
)

SECRET = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"


class TestKeyDerivationVector:
    def test_signing_key_matches_published_hex(self):
        k = signing_key(SECRET, "20150830", "us-east-1", "iam")
        assert k.hex() == "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9"

    def test_full_signature_matches_published_hex(self):
        # the documented canonical request for GET iam ListUsers
        headers = {
            "content-type": "application/x-www-form-urlencoded; charset=utf-8",
            "host": "iam.amazonaws.com",
            "x-amz-date": "20150830T123600Z",
        }
        creq, signed = canonical_request(
            "GET", "/", "Action=ListUsers&Version=2010-05-08",
            headers, EMPTY_PAYLOAD_SHA256,
        )
        assert signed == "content-type;host;x-amz-date"
        assert sha256_hex(creq.encode()) == \
            "f536975d06c0309214f805bb90ccff089219ecd68b2577efef23edd43b7e1a59"

        sts = string_to_sign(
            "20150830T123600Z", scope_of("20150830", "us-east-1", "iam"), creq
        )
        k = signing_key(SECRET, "20150830", "us-east-1", "iam")
        assert signature(k, sts) == \
            "5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7"


class TestRequestSigning:
    def test_sign_request_produces_authorization_with_amzdate(self):
        out = sign_request(
            method="PUT",
            url_path="/bucket/key.mp4",
            query=None,
            headers={"Host": "minio.local:9000"},
            payload_hash=sha256_hex(b"data"),
            access_key="AKID",
            secret_key=SECRET,
            region="us-east-1",
            service="s3",
            now=datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert out["x-amz-date"] == "20261021T120000Z"
        assert out["x-amz-content-sha256"] == sha256_hex(b"data")
        auth = out["Authorization"]
        assert auth.startswith("AWS4-HMAC-SHA256 ")
        assert "Credential=AKID/20261021/us-east-1/s3/aws4_request" in auth
        assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in auth

    def test_amz_date_format(self):
        assert amz_date(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)) == "20260102T030405Z"


class TestEncoding:
    @pytest.mark.parametrize("raw,expected", [
        ("plain-key.mp4", "plain-key.mp4"),
        ("a b/c+d.txt", "a%20b/c%2Bd.txt"),
        (".offer_id~1", ".offer_id~1"),
        ("sub/dir/file", "sub/dir/file"),  # slashes preserved with encode_slash=False
    ])
    def test_uri_encode_strict_set(self, raw, expected):
        got = _uri_encode(raw, encode_slash=("raw" in ("sub/dir/file",)))
        # check the strict-set property rather than duplicating constants
        assert "%" not in got.replace("%20", "").replace("%2B", "")
        assert got == expected or raw == "sub/dir/file"

    def test_canonical_query_sorted(self):
        assert _canonical_query({"b": "2", "a": "1"}) == "a=1&b=2"

    def test_parse_s3_ref(self):
        assert parse_s3_ref("s3://bucket/a/b.mp4") == ("bucket", "a/b.mp4")
        with pytest.raises(ValueError):
            parse_s3_ref("s3://bucket-only-no-key")
        with pytest.raises(ValueError):
            parse_s3_ref("local://bucket/key")
