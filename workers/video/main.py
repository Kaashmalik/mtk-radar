"""Video worker — FFmpeg-driven rendering pipeline.

Weeks 7-8 target (master plan §18): a full video project can be regenerated
from versioned source assets (16:9 + 9:16, captions, thumbnail).

Hard rules (master plan §4):
- Commands come from official docs, tested in a clean environment, with
  expected output documented in the command card.
- Never bake secrets into frames, audio, or project bundles.
- Preserve the versioned project so it can be revised when the offer changes.
"""

# Rendering stages (to be implemented):
#   1. assemble: capture video + narration audio + captions (.srt/.vtt)
#   2. brand: intro/outro template, summary card with steps, expiry, source links
#   3. export: FFmpeg → 16:9 master, 9:16 Shorts/Reels/TikTok cut, thumbnail
#   4. manifest: edit manifest recording every asset + version used
#
# Optional (license review required first — see docs/open-source-integrations.md):
#   Remotion templated React rendering.

if __name__ == "__main__":
    raise NotImplementedError("render pipeline not implemented yet (weeks 7-8)")
