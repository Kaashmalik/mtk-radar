"""HTTP-backed resumable-upload session store (v0.31).

The API owns the short-lived session URI; the worker only holds it in memory
while uploading. Nothing here logs the URI.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx


class APIUploadSessionStore:
    def __init__(self, api: httpx.Client, schedule_id: str):
        self.api = api
        self.schedule_id = schedule_id
        self.path = f"/schedules/{schedule_id}/upload-session"

    def load(self) -> Optional[dict[str, Any]]:
        response = self.api.get(self.path)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("session_uri"):
            raise RuntimeError("upload session store returned an invalid record")
        return payload

    def save(self, session_uri: str, content_length: int) -> dict[str, Any]:
        response = self.api.put(self.path, json={
            "session_uri": session_uri,
            "content_length": int(content_length),
            "provider": "youtube",
        })
        response.raise_for_status()
        return response.json()

    def progress(self, bytes_sent: int) -> None:
        response = self.api.patch(self.path, json={"bytes_sent": int(bytes_sent)})
        response.raise_for_status()

    def clear(self) -> None:
        response = self.api.delete(self.path)
        if response.status_code != 404:
            response.raise_for_status()
