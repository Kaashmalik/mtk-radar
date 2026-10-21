"""Video worker — compatibility entry point (v0.25).

The master plan's repo layout (§12) names `workers/video/` for rendering
jobs, but the pipeline ended up in `workers/render/` (it grew: captions,
narration mixing, project manifests, the auto-render queue). This module
keeps the documented path working instead of leaving a stub that raises
NotImplementedError: every argument is forwarded to the render worker.

    python workers/video/main.py --offer <OFFER_ID> [...]   # → workers/render
    python workers/video/main.py --sweep [--watch]          # → auto-render queue

Nothing is implemented here on purpose — one implementation, two doors.
"""

import os
import runpy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_MAIN = REPO_ROOT / "workers" / "render" / "main.py"


def main() -> None:
    if not RENDER_MAIN.is_file():  # pragma: no cover — broken checkout
        print(f"render worker not found at {RENDER_MAIN}", file=sys.stderr)
        raise SystemExit(1)
    sys.path.insert(0, str(REPO_ROOT / "workers" / "render"))
    sys.path.insert(0, str(REPO_ROOT / "packages"))
    print("note: workers/video/ is an alias for workers/render/ "
          "(the master plan §12 layout) — forwarding the arguments.",
          file=sys.stderr)
    os.chdir(REPO_ROOT)
    runpy.run_path(str(RENDER_MAIN), run_name="__main__")


if __name__ == "__main__":
    main()
