"""Render presets — deterministic, per-platform exports (master plan §5).

16:9 master (YouTube) and 9:16 vertical (Shorts/Reels/TikTok). Capture is
native 1920x1080, so the landscape master never upscales. The vertical preset
keeps the full 16:9 frame (no blind center-crop) on a blurred full-frame
background, then applies motion/captions on top.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    width: int
    height: int
    filter_chain: str        # FFmpeg -vf, or -filter_complex when complex
    video_bitrate: str
    bufsize: str
    audio_bitrate: str
    crf: int
    fps: int
    complex_filter: bool = False


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
    # Full-frame composition: the 16:9 source is fitted on a blurred,
    # edge-filling 9:16 background instead of losing its left/right thirds.
    filter_chain=(
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=24:2[bg2];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[vbase]"
    ),
    video_bitrate="6000k",
    bufsize="12000k",
    audio_bitrate="192k",
    crf=21,
    fps=30,
    complex_filter=True,
)

PRESETS: Final[dict[str, Preset]] = {
    LANDSCAPE.key: LANDSCAPE,
    VERTICAL.key: VERTICAL,
}


def get_preset(key: str) -> Preset:
    if key not in PRESETS:
        raise ValueError(f"unknown preset '{key}' — available: {', '.join(PRESETS)}")
    return PRESETS[key]
