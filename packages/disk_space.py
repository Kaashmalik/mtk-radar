"""Free-disk preflight shared by the render and publishing workers.

The failure it prevents is always confusing: ffmpeg dies mid-encode with an
opaque I/O error and half-written output, or an asset download fills the
storage cache and the post fails mid-materialize. Both workers instead check
FREE space on the target directory BEFORE the work and surface one
operator-actionable message, so the skip/hold states what to do:

    MTK_MIN_FREE_DISK_MB   free-space threshold in MiB (default 2048)
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

DEFAULT_MIN_FREE_MB = 2048
_MB = 1024 * 1024


def min_free_mb() -> int:
    """Operator threshold in MiB (MTK_MIN_FREE_DISK_MB, default 2048)."""
    try:
        value = int(os.environ.get("MTK_MIN_FREE_DISK_MB", DEFAULT_MIN_FREE_MB))
    except ValueError:
        return DEFAULT_MIN_FREE_MB
    return value if value >= 0 else DEFAULT_MIN_FREE_MB


def free_mb(path) -> float:
    """Free space in MiB on the filesystem that holds `path`.

    The path does not need to exist yet (renders/ subfolders and the storage
    cache are created on demand): the nearest EXISTING ancestor is measured.
    """
    probe = Path(path)
    while not probe.exists():
        probe = probe.parent
    return shutil.disk_usage(probe).free / _MB


def low_space(path, *, min_mb: int | None = None) -> str | None:
    """None when `path`'s filesystem has enough free space; otherwise an
    operator-actionable message the caller surfaces with its skip/hold.

    A negative-aware threshold: `free >= min_mb` passes, so a low but
    non-zero threshold still guards the "any space left at all" case.
    """
    threshold = min_free_mb() if min_mb is None else int(min_mb)
    available = free_mb(path)
    if available >= threshold:
        return None
    return (
        f"only {available:.0f} MiB free on the volume holding '{path}' "
        f"(threshold {threshold} MiB, MTK_MIN_FREE_DISK_MB) — free disk "
        "space or lower the threshold; nothing was written"
    )


__all__ = ["DEFAULT_MIN_FREE_MB", "min_free_mb", "free_mb", "low_space"]
