#!/usr/bin/env python3
"""Provider private/test publishing smoke (G01/G02, operator proof).

This is the runnable bridge between "the adapters have private-upload tests"
and "a real provider accepted a private test post". It never publishes a
public post:

* YouTube: uploads with ``privacyStatus=private`` and confirms ``private``.
* Facebook: uploads an unpublished Page video (``published=false``) and
  confirms the draft.
* TikTok: uploads with ``privacy_level=SELF_ONLY`` (TikTok's private/test
  mode) and confirms the completed SELF_ONLY upload.
* Instagram: reports ``unsupported_private`` and makes NO API call. Instagram's
  Content Publishing API has no per-post private/unpublished mode; refusing
  is the correct behavior (see G01), not a failure to work around.

Default mode is dry-run: validate the selected providers and credentials, but
do not contact a provider. Live mode requires an explicit ``--live`` and a
short, already-approved test video. Evidence is JSON and never contains
tokens, refresh tokens, client secrets, or access-token query strings.

Usage (from the repo root):

    python scripts/provider_private_smoke.py --dry-run
    python scripts/provider_private_smoke.py --live --video test-clip.mp4 \
        --providers youtube,facebook,tiktok \
        --evidence-out docs/evidence/provider-private-smoke.json

Credentials are read from the same env names the publishing worker uses:
YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET/YOUTUBE_REFRESH_TOKEN,
FACEBOOK_PAGE_ID/FACEBOOK_PAGE_ACCESS_TOKEN,
TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET/TIKTOK_REFRESH_TOKEN,
INSTAGRAM_USER_ID/INSTAGRAM_ACCESS_TOKEN.

Exit codes: 0 when every selected provider is confirmed (live) or the run is
an informational dry-run with no unexpected error; 1 when a live post is
unconfirmed/failed or a provider reports an unsupported/not-configured state
that prevents proof. A held result is never rewritten as success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHING_ROOT = REPO_ROOT / "workers" / "publishing"
sys.path.insert(0, str(PUBLISHING_ROOT))

from platforms import (  # noqa: E402
    FacebookAdapter,
    NotConfiguredError,
    OAuthConfig,
    TikTokAdapter,
    TikTokConfig,
    YouTubeAdapter,
)

PROVIDERS = ("youtube", "facebook", "tiktok", "instagram")
DEFAULT_PROVIDERS = ("youtube", "facebook", "tiktok")
PRIVATE_MODES = {
    "youtube": "private",
    "facebook": "unpublished_draft",
    "tiktok": "SELF_ONLY",
    "instagram": None,
}
SECRET_ENV_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "CLIENT_KEY", "SIGNING_KEY")
_ACCESS_TOKEN_QUERY = re.compile(r"(?i)(access_token=)[^&\s\"']+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(value: str) -> str:
    """Remove credential values and Graph access-token query parameters.

    Provider errors are useful evidence, but they must never turn a JSON
    artifact into a secret leak. Values shorter than 8 characters are ignored
    so common env placeholders cannot mangle words accidentally.
    """
    text = _ACCESS_TOKEN_QUERY.sub(r"\1[REDACTED]", str(value))
    for name, secret in os.environ.items():
        if not secret or len(secret) < 8:
            continue
        if any(marker in name.upper() for marker in SECRET_ENV_MARKERS):
            text = text.replace(secret, "[REDACTED]")
    return text


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _video_evidence(path: Optional[Path]) -> Optional[dict[str, Any]]:
    if path is None:
        return None
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _youtube_configured() -> bool:
    return OAuthConfig.from_env() is not None


def _facebook_configured() -> bool:
    return bool(os.environ.get("FACEBOOK_PAGE_ID") and
                os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN"))


def _tiktok_configured() -> bool:
    return TikTokConfig.from_env() is not None


def _instagram_configured() -> bool:
    return bool(os.environ.get("INSTAGRAM_USER_ID") and
                os.environ.get("INSTAGRAM_ACCESS_TOKEN"))


def _build_adapter(provider: str):
    if provider == "youtube":
        oauth = OAuthConfig.from_env()
        if oauth is None:
            raise NotConfiguredError(
                "YouTube credentials missing (YOUTUBE_CLIENT_ID, "
                "YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN)")
        return YouTubeAdapter(oauth=oauth)
    if provider == "facebook":
        if not _facebook_configured():
            raise NotConfiguredError(
                "Facebook Page credentials missing (FACEBOOK_PAGE_ID, "
                "FACEBOOK_PAGE_ACCESS_TOKEN)")
        return FacebookAdapter(
            os.environ["FACEBOOK_PAGE_ID"],
            os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"],
        )
    if provider == "tiktok":
        config = TikTokConfig.from_env()
        if config is None:
            raise NotConfiguredError(
                "TikTok credentials missing (TIKTOK_CLIENT_KEY, "
                "TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN)")
        return TikTokAdapter(config=config)
    raise ValueError(f"no adapter for provider {provider!r}")


def _base_result(provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "requested_privacy": "private",
        "platform_privacy": PRIVATE_MODES[provider],
        "checked_at": _now(),
    }


def run_provider(
    provider: str,
    *,
    live: bool,
    video: Optional[Path],
    timeout_s: int,
    interval_s: float,
    adapter_factory: Callable[[str], Any] = _build_adapter,
) -> dict[str, Any]:
    """Run one provider probe and return a JSON-safe result.

    ``adapter_factory`` is injectable so the fail-closed evidence/redaction
    behavior is unit-testable without real credentials or network calls.
    """
    result = _base_result(provider)

    if provider == "instagram":
        # No side effect may happen: Content Publishing has no private mode.
        result.update({
            "status": "unsupported_private",
            "credentials_configured": _instagram_configured(),
            "error": (
                "Instagram Content Publishing has no per-post private/"
                "unpublished mode. This harness refuses to publish a public "
                "post in a private smoke; use a public-post procedure with "
                "explicit human approval instead."),
        })
        return result

    try:
        adapter = adapter_factory(provider)
    except NotConfiguredError as exc:
        result.update({
            "status": "not_configured",
            "credentials_configured": False,
            "error": _redact(str(exc)),
        })
        return result
    except Exception as exc:  # noqa: BLE001 - evidence must record, not crash
        result.update({
            "status": "failed",
            "error": _redact(f"{type(exc).__name__}: {exc}"),
        })
        return result

    result["adapter"] = type(adapter).__name__
    result["credentials_configured"] = True
    if not live:
        result.update({
            "status": "ready",
            "note": "dry-run: credentials present; no provider API call made",
        })
        return result

    assert video is not None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {
        "title": f"MTK RADAR private smoke {stamp}",
        "caption": (
            "Private/test upload generated by the MTK RADAR provider smoke "
            "harness. Not a public post."),
        "tags": ["mtk-radar", "private-smoke"],
        "synthetic_narration": False,
    }
    try:
        adapter.ensure_ready()
        remote_id = adapter.upload(video, meta, privacy="private")
        confirmation = adapter.confirm_publication(
            remote_id,
            expected_privacy="private",
            timeout_s=timeout_s,
            interval_s=interval_s,
        )
    except Exception as exc:  # noqa: BLE001 - held/failed is evidence
        result.update({
            "status": "failed",
            "error": _redact(f"{type(exc).__name__}: {exc}"),
        })
        return result

    confirmed = bool(confirmation.get("confirmed"))
    result.update({
        "status": "confirmed" if confirmed else "held_unconfirmed",
        "remote_id": str(remote_id),
        "confirmation": _json_safe(confirmation),
        "remote_url": confirmation.get("remote_url"),
        "effective_visibility": (
            confirmation.get("visibility")
            or confirmation.get("processing_state")
            or PRIVATE_MODES[provider]
        ),
    })
    if not confirmed:
        result["error"] = _redact(
            confirmation.get("error")
            or "provider accepted the upload but did not confirm the private "
               "post before the deadline; verify manually and do not retry "
               "blindly")
    return result


def _json_safe(value: Any) -> Any:
    """Provider confirmation payloads must be JSON-serializable evidence."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _redact(str(value))


def run_smoke(
    *,
    providers: list[str],
    live: bool,
    video: Optional[Path],
    timeout_s: int = 300,
    interval_s: float = 5.0,
    adapter_factory: Callable[[str], Any] = _build_adapter,
) -> dict[str, Any]:
    started = _now()
    results = {
        provider: run_provider(
            provider,
            live=live,
            video=video,
            timeout_s=timeout_s,
            interval_s=interval_s,
            adapter_factory=adapter_factory,
        )
        for provider in providers
    }
    statuses = {name: item["status"] for name, item in results.items()}
    if live:
        ok = bool(results) and all(status == "confirmed" for status in statuses.values())
    else:
        ok = all(status not in {"failed", "held_unconfirmed"} for status in statuses.values())
    return {
        "schema": "mtk-provider-private-smoke/1",
        "mode": "live" if live else "dry-run",
        "started_at": started,
        "finished_at": _now(),
        "video": _video_evidence(video),
        "providers": results,
        "statuses": statuses,
        "ok": ok,
        "proven": bool(live and ok),
        "proof": (
            "live_private_posts_confirmed" if live and ok
            else "dry_run_only" if not live
            else "not_proven"
        ),
        "notes": [
            "A private smoke never publishes a public post.",
            "Instagram is reported unsupported_private by design (no private mode).",
            "TikTok private/unlisted is SELF_ONLY; completion does not prove public visibility.",
            "Tokens and access-token query strings are redacted from this artifact.",
        ],
    }


def _parse_providers(raw: str) -> list[str]:
    requested = [p.strip().lower() for p in raw.split(",") if p.strip()]
    if requested == ["all"]:
        requested = list(PROVIDERS)
    unknown = sorted(set(requested) - set(PROVIDERS))
    if unknown:
        raise ValueError(f"unknown provider(s): {', '.join(unknown)}")
    if not requested:
        raise ValueError("at least one provider is required")
    # Preserve user order while removing duplicates.
    return list(dict.fromkeys(requested))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Private/test publishing smoke for the paid providers.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true",
                      help="upload real private/test posts (explicit opt-in)")
    mode.add_argument("--dry-run", action="store_true",
                      help="validate configuration only (default)")
    parser.add_argument("--providers", default=",".join(DEFAULT_PROVIDERS),
                        help="comma-separated: youtube,facebook,tiktok,instagram,all")
    parser.add_argument("--video", type=Path,
                        help="short approved video used for live uploads")
    parser.add_argument("--timeout", type=int, default=300,
                        help="confirmation deadline per provider (seconds)")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="confirmation poll interval (seconds)")
    parser.add_argument("--evidence-out", type=Path,
                        help="write the JSON evidence artifact to this path")
    args = parser.parse_args(argv)

    try:
        providers = _parse_providers(args.providers)
    except ValueError as exc:
        parser.error(str(exc))

    if args.live and args.video is None:
        parser.error("--live requires --video pointing at an approved test clip")
    if args.live and (not args.video.exists() or args.video.stat().st_size == 0):
        parser.error(f"--video is missing or empty: {args.video}")
    if args.interval < 0 or args.timeout < 0:
        parser.error("--timeout and --interval must be non-negative")

    evidence = run_smoke(
        providers=providers,
        live=bool(args.live),
        video=args.video,
        timeout_s=args.timeout,
        interval_s=args.interval,
    )
    payload = json.dumps(evidence, indent=2, sort_keys=True)
    print(payload)
    if args.evidence_out:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(payload + "\n", encoding="utf-8")
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
