"""Local filesystem driver — same interface as the S3 driver.

Refs are `local://<key>`; the on-disk root comes from env
(MTK_STORAGE_LOCAL_ROOT, default ./storage) at resolution time, so DB-stored
refs stay portable across hosts that share the root (NFS/bind mount) — and
multi-host only truly works with the s3:// backend.
"""

import os
import shutil
from pathlib import Path

SCHEME = "local"


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, local_path: Path, key: str) -> str:
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        # temp + rename so a crash never leaves a partial object behind
        tmp = dest.with_suffix(dest.suffix + ".partial")
        shutil.copyfile(local_path, tmp)
        tmp.replace(dest)
        return f"{SCHEME}://{key}"

    def get(self, ref: str, dest: Path) -> Path:
        key = self.parse_ref(ref)
        src = self.root / key
        if not src.exists():
            raise FileNotFoundError(f"not in local storage root: {key}")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return dest

    def exists(self, ref: str) -> bool:
        return (self.root / self.parse_ref(ref)).exists()

    def delete(self, ref: str) -> None:
        path = self.root / self.parse_ref(ref)
        path.unlink(missing_ok=True)

    @staticmethod
    def parse_ref(ref: str) -> str:
        if not ref.startswith(f"{SCHEME}://"):
            raise ValueError(f"not a local storage ref: {ref!r}")
        key = ref[len(SCHEME) + 3:]
        if not key or key.startswith("/") or ".." in Path(key).parts:
            raise ValueError(f"unsafe local storage key: {ref!r}")
        return key


def root_from_env() -> Path:
    return Path(os.environ.get("MTK_STORAGE_LOCAL_ROOT", "./storage"))
