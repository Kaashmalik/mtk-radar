"""Public media URL (v0.19): Instagram (and TikTok-style platforms) need the
platform to FETCH the media from a public https URL — the worker must derive
that URL from the managed storage ref, or fail with an actionable message.
"""

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "mtk_publishing_main", Path(__file__).resolve().parent.parent / "main.py")
pub = importlib.util.module_from_spec(_spec)
sys.modules["mtk_publishing_main"] = pub
_spec.loader.exec_module(pub)


def test_s3_ref_becomes_a_public_url(monkeypatch):
    monkeypatch.setenv("MTK_PUBLIC_MEDIA_BASE_URL", "https://cdn.example.com/")
    # the bucket stays in the path — same layout as the S3 driver uses
    assert pub.public_media_url("s3://mtk-radar/renders/off-1-landscape.mp4") == \
        "https://cdn.example.com/mtk-radar/renders/off-1-landscape.mp4"


def test_local_ref_becomes_a_public_url(monkeypatch):
    monkeypatch.setenv("MTK_PUBLIC_MEDIA_BASE_URL", "https://files.example.com")
    assert pub.public_media_url("local://renders/off-1.mp4") == \
        "https://files.example.com/renders/off-1.mp4"


def test_without_a_public_base_there_is_no_url(monkeypatch):
    monkeypatch.delenv("MTK_PUBLIC_MEDIA_BASE_URL", raising=False)
    assert pub.public_media_url("s3://mtk-radar/renders/off-1.mp4") is None


def test_plain_paths_are_not_turned_into_urls(monkeypatch):
    monkeypatch.setenv("MTK_PUBLIC_MEDIA_BASE_URL", "https://cdn.example.com")
    assert pub.public_media_url("projects/off-1/renders/off-1.mp4") is None


def test_empty_ref_is_safe(monkeypatch):
    monkeypatch.setenv("MTK_PUBLIC_MEDIA_BASE_URL", "https://cdn.example.com")
    assert pub.public_media_url("") is None
    assert os.environ["MTK_PUBLIC_MEDIA_BASE_URL"] == "https://cdn.example.com"
