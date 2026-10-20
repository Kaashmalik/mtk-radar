"""Render presets — deterministic, per-platform exports (master plan §5).

16:9 master (YouTube) and 9:16 vertical (Shorts/Reels/TikTok). Sources are
recorded at 1280x720; the vertical preset centers a 1080x1920 crop.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    width: int
    height: int
    filter_chain: str        # FFmpeg -vf for a 1280x720 source
    video_bitrate: str
    bufsize: str
    audio_bitrate: str
    crf: int
    fps: int


LANDSCAPE: Final = Preset(
    key="landscape",
    label="16:9 master (YouTube)",
    width=1920,
    height=1080,
    filter_chain="scale=1920:1080:flags=lanczos",
    video_bitrate="5000k",
    bufsize="10000k",
    audio_bitrate="192k",
    crf=21,
    fps=30,
)

VERTICAL: Final = Preset(
    key="vertical",
    label="9:16 Shorts/Reels/TikTok",
    width=1080,
    height=1920,
    filter_chain="scale=-2:1920:flags=lanczos,crop=1080:1920",
    video_bitrate="6000k",
    bufsize="12000k",
    audio_bitrate="192k",
    crf=21,
    fps=30,
)

PRESETS: Final[dict[str, Preset]] = {
    LANDSCAPE.key: LANDSCAPE,
    VERTICAL.key: VERTICAL,
}


def get_preset(key: str) -> Preset:
    if key not in PRESETS:
        raise ValueError(f"unknown preset '{key}' — available: {', '.join(PRESETS)}")
    return PRESETS[key]
