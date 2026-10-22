"""YouTube adapter — official Data API resumable upload (§6, docs:
https://developers.google.com/youtube/v3/docs/videos/insert).

Auth: OAuth2 refresh-token flow. Access tokens are held IN MEMORY ONLY and
refreshed when near expiry or on a 401; refresh expiry is reported back via
the on_refresh hook (never the token). Privacy status comes from the schedule
(private by default for test uploads).
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from .base import (
    PublishAdapter,
    TokenExpiredError,
    TransportUnauthorized,
)

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_INIT_URL = (
    "https://www.googleapis.com/upload/youtube/v3/videos"
    "?uploadType=resumable&part=snippet,status"
)
TOKEN_MIN_TTL_S = 120  # refresh before expiry with margin
CATEGORY_DEVELOPER = "28"  # Science & Technology
DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024  # YouTube requires a multiple of 256 KiB
_ISO_DURATION = re.compile(
    r"^PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?$")
_RANGE_DONE = re.compile(r"^bytes=0-(?P<last>\d+)$")

log = logging.getLogger("youtube")


def _parse_iso8601_duration(value: str) -> Optional[float]:
    match = _ISO_DURATION.match(str(value or ""))
    if not match:
        return None
    return (
        int(match.group("h") or 0) * 3600
        + int(match.group("m") or 0) * 60
        + float(match.group("s") or 0)
    )


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls, prefix: str = "YOUTUBE_") -> Optional["OAuthConfig"]:
        import os

        prefix = (prefix or "YOUTUBE_").rstrip("_*") + "_"
        cfg = cls(
            client_id=os.environ.get(f"{prefix}CLIENT_ID", ""),
            client_secret=os.environ.get(f"{prefix}CLIENT_SECRET", ""),
            refresh_token=os.environ.get(f"{prefix}REFRESH_TOKEN", ""),
        )
        return cfg if all([cfg.client_id, cfg.client_secret, cfg.refresh_token]) else None


class YouTubeAdapter(PublishAdapter):
    platform = "youtube"

    def __init__(self, oauth: Optional[OAuthConfig] = None,
                 access_token: Optional[str] = None,
                 account_id: Optional[str] = None,
                 on_refresh=None,
                 http: Optional[httpx.Client] = None):
        super().__init__(account_id=account_id, on_refresh=on_refresh)
        self.oauth = oauth
        self._access = access_token
        self._expires_monotonic = 0.0
        self._http = http or httpx.Client(timeout=600)
        self._session_store = None
        try:
            chunk = int(os.environ.get(
                "MTK_YOUTUBE_UPLOAD_CHUNK_BYTES", DEFAULT_CHUNK_BYTES))
        except ValueError as exc:
            raise ValueError("MTK_YOUTUBE_UPLOAD_CHUNK_BYTES must be an integer") from exc
        if chunk <= 0 or chunk % (256 * 1024):
            raise ValueError(
                "MTK_YOUTUBE_UPLOAD_CHUNK_BYTES must be a multiple of 256 KiB")
        self._chunk_bytes = chunk

    def set_upload_session_store(self, store) -> None:
        """Attach a worker-owned persisted session store for resume support."""
        self._session_store = store

    # ------------------------------------------------------------------ auth

    def ensure_ready(self) -> None:
        self._ensure_token()

    def _ensure_token(self, force: bool = False) -> None:
        if not force and self._access and (self._expires_monotonic - time.monotonic()) > TOKEN_MIN_TTL_S:
            return
        if self.oauth is None:
            if self._access:
                self._expires_monotonic = time.monotonic() + 3600  # static test token
                return
            raise TokenExpiredError("YouTube credentials missing (YOUTUBE_* env not configured)")
        self._force_refresh()

    def _force_refresh(self) -> None:
        try:
            resp = self._http.post(
                TOKEN_URL,
                data={
                    "client_id": self.oauth.client_id,
                    "client_secret": self.oauth.client_secret,
                    "refresh_token": self.oauth.refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code in (400, 401):
                raise TokenExpiredError(
                    f"refresh rejected ({resp.status_code}) — operator must re-consent"
                )
            resp.raise_for_status()
            data = resp.json()
        except TokenExpiredError:
            raise
        except Exception as exc:  # noqa: BLE001 — network errors must not loop forever
            raise TokenExpiredError(f"token refresh failed: {exc}") from exc

        self._access = data["access_token"]
        ttl = int(data.get("expires_in", 3600))
        self._expires_monotonic = time.monotonic() + ttl
        if self.account_id and self.on_refresh:
            self.on_refresh(datetime.now(timezone.utc) + timedelta(seconds=ttl))

    # ---------------------------------------------------------------- upload

    def upload(self, video_path: Path, meta: dict[str, Any],
               privacy: str = "private", idempotency_key: str | None = None) -> str:
        self._ensure_token()
        try:
            return self._do_upload(video_path, meta, privacy, idempotency_key)
        except TransportUnauthorized:
            # token-expiry recovery: refresh once, retry once (§6)
            self._force_refresh()
            return self._do_upload(video_path, meta, privacy, idempotency_key)

    def _do_upload(self, video_path: Path, meta: dict[str, Any],
                   privacy: str, idempotency_key: str | None) -> str:
        # Upload the approved package verbatim. Chapters are already in the
        # description and covered by the schedule's metadata hash; editing it
        # here would make the uploaded bytes differ from what was reviewed.
        description = str(meta.get("caption") or "")[:5000]
        tags = meta.get("tags") or []
        body = {
            "snippet": {
                "title": str(meta.get("title") or "MTK RADAR AI")[:100],
                "description": description,
                "tags": tags[:30] if isinstance(tags, list) else [],
                "categoryId": CATEGORY_DEVELOPER,
            },
            "status": {
                "privacyStatus": privacy if privacy in ("public", "unlisted", "private") else "private",
                "selfDeclaredMadeForKids": False,
            },
        }
        total = Path(video_path).stat().st_size

        if self._session_store is not None:
            return self._do_resumable_upload(video_path, body, total)

        # Legacy path: a single PUT. Idempotency keys are accepted for the
        # adapter interface but YouTube does not dedupe uploads by request id.
        headers = {
            "Authorization": f"Bearer {self._access}",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(total),
        }
        init = self._http.post(UPLOAD_INIT_URL, json=body, headers=headers)
        if init.status_code == 401:
            raise TransportUnauthorized("upload init rejected: token invalid")
        init.raise_for_status()

        location = init.headers.get("location")
        if not location:
            raise RuntimeError("YouTube did not return a resumable session location")

        with open(video_path, "rb") as fh:
            upload = self._http.put(
                location, content=fh,
                headers={"Content-Type": "video/mp4"},
            )
        if upload.status_code == 401:
            raise TransportUnauthorized("upload rejected: token expired mid-flight")
        upload.raise_for_status()
        return str(upload.json()["id"])

    # ------------------------------------------------- persisted resume (v0.31)

    def _init_session(self, body: dict[str, Any], total: int) -> str:
        headers = {
            "Authorization": f"Bearer {self._access}",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(total),
        }
        init = self._http.post(UPLOAD_INIT_URL, json=body, headers=headers)
        if init.status_code == 401:
            raise TransportUnauthorized("upload init rejected: token invalid")
        init.raise_for_status()
        location = init.headers.get("location")
        if not location:
            raise RuntimeError("YouTube did not return a resumable session location")
        return location

    @staticmethod
    def _range_offset(value: str | None) -> int | None:
        if not value:
            return None
        match = _RANGE_DONE.fullmatch(value.strip())
        return int(match.group("last")) + 1 if match else None

    def _query_session(self, uri: str, total: int) -> tuple[str, int | str]:
        """Ask YouTube what it actually received.

        Returns ("complete", video_id), ("offset", next_byte) or
        ("expired", 0). A query carries no video bytes.
        """
        response = self._http.put(
            uri,
            content=b"",
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes */{total}",
            },
        )
        if response.status_code == 401:
            raise TransportUnauthorized("resume status rejected: token invalid")
        if response.status_code in (404, 410):
            return "expired", 0
        if response.status_code in (200, 201):
            video_id = (response.json() or {}).get("id")
            if not video_id:
                raise RuntimeError("completed upload response had no video id")
            return "complete", str(video_id)
        if response.status_code == 308:
            offset = self._range_offset(response.headers.get("range"))
            if offset is None:
                # No bytes are confirmed yet; resend from the start.
                return "offset", 0
            if offset > total:
                raise RuntimeError("provider reported progress beyond file size")
            return "offset", offset
        response.raise_for_status()
        raise RuntimeError(f"unexpected resume status {response.status_code}")

    def _do_resumable_upload(self, video_path: Path, body: dict[str, Any],
                             total: int) -> str:
        if total <= 0:
            raise RuntimeError("refusing to upload an empty video")
        store = self._session_store
        existing = store.load()
        offset = 0
        if existing:
            if int(existing.get("content_length", -1)) != total:
                store.clear()
                raise RuntimeError(
                    "persisted upload session size does not match the rendered file")
            uri = str(existing["session_uri"])
            state, observed = self._query_session(uri, total)
            if state == "complete":
                self._clear_session_quietly()
                return str(observed)
            if state == "expired":
                store.clear()
                existing = None
            else:
                offset = int(observed)
                # Persist the provider-observed offset, not what we attempted.
                store.progress(offset)

        if not existing:
            uri = self._init_session(body, total)
            # Persist BEFORE sending bytes: if the worker dies after the first
            # chunk, the next attempt can resume instead of uploading a
            # duplicate video.
            store.save(uri, total)

        with open(video_path, "rb") as fh:
            while offset < total:
                fh.seek(offset)
                chunk = fh.read(min(self._chunk_bytes, total - offset))
                if not chunk:
                    raise RuntimeError("video ended before its recorded size")
                end = offset + len(chunk) - 1
                response = self._http.put(
                    uri,
                    content=chunk,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes {offset}-{end}/{total}",
                    },
                )
                if response.status_code == 401:
                    raise TransportUnauthorized(
                        "upload rejected: token expired mid-flight")
                if response.status_code in (200, 201):
                    video_id = (response.json() or {}).get("id")
                    if not video_id:
                        raise RuntimeError("completed upload response had no video id")
                    self._clear_session_quietly()
                    return str(video_id)
                if response.status_code == 308:
                    next_offset = self._range_offset(response.headers.get("range"))
                    if next_offset is None:
                        raise RuntimeError(
                            "YouTube accepted a chunk without reporting its range")
                    if next_offset <= offset:
                        raise RuntimeError("upload progress did not advance")
                    store.progress(next_offset)
                    offset = next_offset
                    continue
                response.raise_for_status()
                raise RuntimeError(
                    f"unexpected chunk response {response.status_code}")
        raise RuntimeError("upload ended without a video id")

    def _clear_session_quietly(self) -> None:
        try:
            self._session_store.clear()
        except Exception as exc:  # noqa: BLE001 - row expires; never lose a video id
            log.warning("could not clear persisted upload session: %s", exc)

    # --------------------------------------- complete YouTube package (v0.28)

    def _headers(self) -> dict[str, str]:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access}"}

    def set_thumbnail(self, video_id: str, image_path: Path) -> dict:
        """Upload the reviewed cover as the custom thumbnail.

        YouTube requires JPEG/PNG <= 2MB. SVG covers are a canonical source
        asset, not an uploadable thumbnail; record that as an operator task.
        """
        path = Path(image_path)
        suffix = path.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg"):
            raise RuntimeError(
                f"thumbnail {path.name} must be PNG/JPEG (SVG needs conversion)")
        data = path.read_bytes()
        if len(data) > 2 * 1024 * 1024:
            raise RuntimeError("thumbnail exceeds YouTube's 2MB limit")
        content_type = "image/png" if suffix == ".png" else "image/jpeg"
        resp = self._http.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params={"videoId": video_id, "uploadType": "media"},
            content=data,
            headers={**self._headers(), "Content-Type": content_type},
        )
        if resp.status_code == 401:
            raise TransportUnauthorized("thumbnails.set rejected: token invalid")
        if resp.status_code >= 300:
            raise RuntimeError(f"thumbnails.set failed ({resp.status_code}): {resp.text[:300]}")
        return {"ok": True, "bytes": len(data)}

    def upload_captions(self, video_id: str, captions_path: Path,
                        language: str = "en", name: str | None = None) -> dict:
        """Insert a caption track (multipart upload, official captions.insert)."""
        path = Path(captions_path)
        suffix = path.suffix.lower()
        if suffix not in (".srt", ".vtt"):
            raise RuntimeError(f"captions must be .srt or .vtt (got {path.name})")
        snippet = json.dumps({
            "videoId": video_id,
            "language": language,
            "name": name or ("English" if language == "en" else language),
            "isDraft": False,
        })
        content_type = "text/vtt" if suffix == ".vtt" else "application/x-subrip"
        resp = self._http.post(
            "https://www.googleapis.com/upload/youtube/v3/captions",
            params={"part": "snippet", "uploadType": "multipart"},
            data={"snippet": snippet},
            files={"file": (path.name, path.read_bytes(), content_type)},
            headers=self._headers(),
        )
        if resp.status_code == 401:
            raise TransportUnauthorized("captions.insert rejected: token invalid")
        if resp.status_code >= 300:
            raise RuntimeError(f"captions.insert failed ({resp.status_code}): {resp.text[:300]}")
        return {"ok": True, "id": (resp.json() or {}).get("id"), "language": language}

    def add_to_playlist(self, video_id: str, playlist_id: str) -> dict:
        resp = self._http.post(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "snippet"},
            json={"snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }},
            headers=self._headers(),
        )
        if resp.status_code == 401:
            raise TransportUnauthorized("playlistItems.insert rejected: token invalid")
        if resp.status_code >= 300:
            raise RuntimeError(
                f"playlistItems.insert failed ({resp.status_code}): {resp.text[:300]}")
        return {"ok": True, "playlist_id": playlist_id,
                "id": (resp.json() or {}).get("id")}

    def post_comment(self, video_id: str, text: str) -> dict:
        """Create the approved top-level comment.

        The public Data API has no pin operation. We post the comment and
        return `pinned: false` + an operator action, rather than pretending
        the comment was pinned.
        """
        body = str(text or "").strip()
        if not body:
            return {"ok": True, "skipped": "empty comment"}
        resp = self._http.post(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params={"part": "snippet"},
            json={"snippet": {
                "videoId": video_id,
                "topLevelComment": {"snippet": {"textOriginal": body[:10000]}},
            }},
            headers=self._headers(),
        )
        if resp.status_code == 401:
            raise TransportUnauthorized("commentThreads.insert rejected: token invalid")
        if resp.status_code >= 300:
            raise RuntimeError(
                f"commentThreads.insert failed ({resp.status_code}): {resp.text[:300]}")
        return {"ok": True, "id": (resp.json() or {}).get("id"),
                "pinned": False,
                "operator_action": "Pin this comment in YouTube Studio (API cannot pin)."}

    def finalize_package(self, video_id: str, meta: dict[str, Any], *,
                         thumbnail_path: Optional[Path] = None,
                         captions_path: Optional[Path] = None,
                         playlist_id: Optional[str] = None,
                         pinned_comment: Optional[str] = None,
                         captions_language: Optional[str] = None) -> dict:
        """Attach every requested YouTube asset after upload.

        A requested asset is mandatory: the package is not complete unless the
        thumbnail, captions, playlist entry and comment were all accepted.
        Omitted assets are explicit skips. The worker holds an upload whose
        package is incomplete instead of reporting a successful release. A
        dead token is re-raised so the worker pauses the queue.
        """
        result: dict[str, Any] = {}
        requested = {
            "thumbnail": bool(thumbnail_path),
            "captions": bool(captions_path),
            "playlist": bool(playlist_id),
            "comment": bool(pinned_comment),
        }
        operations = [
            ("thumbnail", lambda: self.set_thumbnail(video_id, thumbnail_path)
             if thumbnail_path else {"ok": True, "skipped": "no cover"}),
            ("captions", lambda: self.upload_captions(
                video_id, captions_path,
                language=str(captions_language
                             or meta.get("captions_language") or "en"))
             if captions_path else {"ok": True, "skipped": "no captions"}),
            ("playlist", lambda: self.add_to_playlist(video_id, playlist_id)
             if playlist_id else {"ok": True, "skipped": "no playlist"}),
            ("comment", lambda: self.post_comment(video_id, pinned_comment or "")
             if pinned_comment else {"ok": True, "skipped": "no pinned comment"}),
        ]
        failures: dict[str, str] = {}
        for name, operation in operations:
            try:
                outcome = operation()
                result[name] = outcome
                if not outcome.get("ok", False):
                    failures[name] = str(outcome.get("error") or "not accepted")
            except TransportUnauthorized:
                raise
            except Exception as exc:  # noqa: BLE001 — recorded as package failure
                result[name] = {"ok": False, "error": str(exc)}
                failures[name] = str(exc)
        result["mandatory"] = sorted(name for name, needed in requested.items() if needed)
        result["failures"] = failures
        result["complete"] = not failures
        return result

    def confirm_publication(self, video_id: str, *, expected_privacy: str,
                            timeout_s: int = 300,
                            interval_s: float = 5.0) -> dict:
        """Poll videos.list until YouTube has processed the upload and the
        visibility matches the approved schedule. No confirmation = not
        published (the worker reports a held failure, never success)."""
        deadline = time.monotonic() + max(0, int(timeout_s))
        last: dict[str, Any] = {}
        while True:
            resp = self._http.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "status,processingDetails,snippet", "id": video_id},
                headers=self._headers(),
            )
            if resp.status_code == 401:
                raise TransportUnauthorized("videos.list rejected: token invalid")
            resp.raise_for_status()
            items = (resp.json() or {}).get("items") or []
            if items:
                item = items[0]
                status = item.get("status") or {}
                processing = item.get("processingDetails") or {}
                upload_status = status.get("uploadStatus")
                processing_status = processing.get("processingStatus")
                privacy = status.get("privacyStatus")
                last = {
                    "remote_url": f"https://www.youtube.com/watch?v={video_id}",
                    "upload_status": upload_status,
                    "processing_status": processing_status,
                    "privacy": privacy,
                }
                if upload_status in ("failed", "rejected", "deleted") \
                        or processing_status in ("failed", "terminated"):
                    return {**last, "confirmed": False,
                            "error": f"remote terminal state: {upload_status}/{processing_status}"}
                privacy_ok = privacy == expected_privacy
                processed = upload_status == "processed" and \
                    processing_status in (None, "succeeded")
                if processed and privacy_ok:
                    return {**last, "confirmed": True,
                            "processing_state": processing_status or upload_status}
            if time.monotonic() >= deadline:
                return {**last, "confirmed": False,
                        "error": "upload is still processing or visibility is not yet "
                                 "confirmed — verify in YouTube Studio before retrying"}
            time.sleep(max(0.1, interval_s))

    # ------------------------------------------------- analytics & corrections

    def access_token(self) -> str:
        """Valid bearer token for auxiliary YouTube APIs (analytics reports).
        Refreshes like the upload path so the metrics worker can reuse one
        adapter instance across a sweep."""
        self._ensure_token()
        assert self._access
        return self._access

    def fetch_video_metrics(self, video_id: str) -> dict:
        """Per-video audience metrics via the official YouTube Analytics API v2
        (docs: https://developers.google.com/youtube/analytics). Requires the
        OAuth grant to include the yt-analytics scope — without it the API
        answers 403 and the caller should skip (documented gap, not an error).

        The full metric set is requested first. Older/limited channels can
        reject impressions or subscriber metrics with 400; we then fall back
        to the universally available subset rather than losing the snapshot.
        """
        self._ensure_token()
        headers = {"Authorization": f"Bearer {self._access}"}
        base = {
            "ids": "channel==MINE",
            "startDate": "2000-01-01",
            "endDate": datetime.now(timezone.utc).date().isoformat(),
            "filters": f"video=={video_id}",
        }
        full = (
            "views,likes,comments,shares,averageViewDuration,"
            "averageViewPercentage,subscribersGained,subscribersLost,"
            "impressions,impressionClickThroughRate,estimatedMinutesWatched"
        )
        resp = self._http.get(
            "https://youtubeanalytics.googleapis.com/v2/reports",
            params={**base, "metrics": full},
            headers=headers,
        )
        if resp.status_code == 403:
            raise PermissionError("yt-analytics scope not granted for this OAuth client")
        if resp.status_code == 400:
            resp = self._http.get(
                "https://youtubeanalytics.googleapis.com/v2/reports",
                params={**base, "metrics": "views,likes,comments,shares,averageViewDuration"},
                headers=headers,
            )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("rows") or []
        if not rows:
            return {}
        cols = [c["name"] for c in data.get("columnHeaders", [])]
        metrics = dict(zip(cols, rows[0]))
        # 3-second retention comes from a separate audienceWatchRatio report
        # because it uses a dimension, not a scalar metric.
        try:
            retention = self.fetch_retention_3s(video_id)
            if retention is not None:
                metrics["retention_3s"] = retention
        except Exception:  # noqa: BLE001 — retention is additive, not a blocker
            pass
        return metrics

    def fetch_retention_3s(self, video_id: str) -> Optional[float]:
        """Approximate 3-second retention from audienceWatchRatio.

        YouTube exposes the retention curve by elapsedVideoTimeRatio. We look
        up the video duration, convert 3 seconds to a ratio, and pick the
        closest bucket. Returns None when the report/scope is unavailable.
        """
        duration = self._video_duration_s(video_id)
        if not duration or duration <= 0:
            return None
        if duration <= 3:
            return 1.0
        self._ensure_token()
        resp = self._http.get(
            "https://youtubeanalytics.googleapis.com/v2/reports",
            params={
                "ids": "channel==MINE",
                "startDate": "2000-01-01",
                "endDate": datetime.now(timezone.utc).date().isoformat(),
                "metrics": "audienceWatchRatio",
                "dimensions": "elapsedVideoTimeRatio",
                "filters": f"video=={video_id}",
                "sort": "elapsedVideoTimeRatio",
                "maxResults": 200,
            },
            headers={"Authorization": f"Bearer {self._access}"},
        )
        if resp.status_code in (400, 403):
            return None
        resp.raise_for_status()
        rows = resp.json().get("rows") or []
        if not rows:
            return None
        target = min(1.0, 3.0 / float(duration))
        closest = min(rows, key=lambda row: abs(float(row[0]) - target))
        return float(closest[1]) if closest[1] is not None else None

    def _video_duration_s(self, video_id: str) -> Optional[float]:
        self._ensure_token()
        resp = self._http.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "contentDetails", "id": video_id},
            headers={"Authorization": f"Bearer {self._access}"},
        )
        if resp.status_code in (400, 403, 404):
            return None
        resp.raise_for_status()
        items = resp.json().get("items") or []
        if not items:
            return None
        return _parse_iso8601_duration(
            (items[0].get("contentDetails") or {}).get("duration", ""))

    def apply_correction_notice(self, video_id: str, notice: str) -> None:
        """§11: push a correction notice into an ALREADY-published description.
        videos.update requires the full snippet (categoryId included), so this
        is list → merge → update; the description is replaced with current +
        notice appended to keep the operation idempotent-safe."""
        self._ensure_token()
        headers = {"Authorization": f"Bearer {self._access}"}
        listing = self._http.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet", "id": video_id},
            headers=headers,
        )
        if listing.status_code == 401:
            raise TransportUnauthorized("videos.list rejected: token invalid")
        listing.raise_for_status()
        items = listing.json().get("items") or []
        if not items:
            raise RuntimeError(f"video {video_id} not visible to this credential")
        snippet = items[0]["snippet"]
        current = str(snippet.get("description") or "")
        # Retrying after a lost response must not append the notice twice.
        description = current if notice in current else \
            f"{current.rstrip()}\n\n{notice}".strip()
        # videos.update replaces the snippet with exactly what is sent. Preserve
        # every mutable field we do not intend to change (notably tags and the
        # declared language), otherwise a correction would wipe them.
        updated_snippet = {
            "title": snippet.get("title", ""),
            "description": description,
            "categoryId": snippet.get("categoryId") or CATEGORY_DEVELOPER,
        }
        for field in ("tags", "defaultLanguage", "defaultAudioLanguage"):
            if snippet.get(field):
                updated_snippet[field] = snippet[field]

        update = self._http.put(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet"},
            json={"id": video_id, "snippet": updated_snippet},
            headers=headers,
        )
        if update.status_code == 401:
            raise TransportUnauthorized("videos.update rejected: token expired")
        update.raise_for_status()
