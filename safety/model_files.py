"""Shared checks for staged moderation weights.

A Git LFS pointer is a text stub, not a checkpoint. Callers must treat it as
missing so inference never claims a trained model ran.
"""
from __future__ import annotations

from pathlib import Path

_LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"


def is_git_lfs_pointer(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > 1024:
            return False
        with path.open("rb") as handle:
            return handle.read(len(_LFS_PREFIX)) == _LFS_PREFIX
    except OSError:
        return False
