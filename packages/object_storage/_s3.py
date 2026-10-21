"""S3-compatible driver (AWS S3, MinIO, R2, B2) over httpx + SigV4.

Path-style addressing ({endpoint}/{bucket}/{key}) — the norm for MinIO and
self-hosted stores. Refs are `s3://<bucket>/<key>`.
"""

from pathlib import Path
from typing import Any

import httpx

from ._sigv4 import (
    EMPTY_PAYLOAD_SHA256,
    amz_date,
    object_url_encode,
    parse_s3_ref,
    sha256_hex,
    sign_request,
)

SERVICE = "s3"


class S3Storage:
    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        http: httpx.Client | None = None,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self._http = http or httpx.Client(timeout=300)

    # ------------------------------------------------------------ refs

    @staticmethod
    def parse_ref(ref: str) -> tuple[str, str]:
        return parse_s3_ref(ref)

    def _url(self, bucket: str, key: str) -> str:
        return f"{self.endpoint}/{bucket}/{object_url_encode(key)}"

    def _signed(
        self,
        method: str,
        bucket: str,
        key: str,
        body: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = self._url(bucket, key)
        payload_hash = sha256_hex(body) if body is not None else EMPTY_PAYLOAD_SHA256
        host = httpx.URL(url).host
        if httpx.URL(url).port:
            host = f"{host}:{httpx.URL(url).port}"
        headers: dict[str, str] = {"Host": host, **(extra_headers or {})}
        headers = sign_request(
            method=method,
            url_path=f"/{bucket}/{object_url_encode(key)}",
            query=None,
            headers=headers,
            payload_hash=payload_hash,
            access_key=self.access_key,
            secret_key=self.secret_key,
            region=self.region,
            service=SERVICE,
        )
        return self._http.request(
            method, url, content=body, headers=headers
        ) if body is not None else self._http.request(method, url, headers=headers)

    # ------------------------------------------------------------ API

    def put(self, local_path: Path, key: str) -> str:
        """Upload local_path → s3://bucket/key; returns the ref for the DB."""
        body = Path(local_path).read_bytes()
        resp = self._signed("PUT", self.bucket, key, body=body)
        resp.raise_for_status()
        return f"s3://{self.bucket}/{key}"

    def get(self, ref: str, dest: Path) -> Path:
        bucket, key = self.parse_ref(ref)
        resp = self._signed("GET", bucket, key)
        if resp.status_code == 404:
            raise FileNotFoundError(f"object not found: {ref}")
        resp.raise_for_status()
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return dest

    def exists(self, ref: str) -> bool:
        bucket, key = self.parse_ref(ref)
        return self._signed("HEAD", bucket, key).status_code == 200

    def delete(self, ref: str) -> None:
        bucket, key = self.parse_ref(ref)
        self._signed("DELETE", bucket, key).raise_for_status()
