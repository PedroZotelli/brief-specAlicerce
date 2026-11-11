"""Operating-system differences that Brief-Spec must handle in one place."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

# Reparse tags that redirect a path elsewhere on Windows. Other reparse points
# (cloud-sync placeholders, deduplicated files) are ordinary files here.
_IO_REPARSE_TAG_SYMLINK = 0xA000000C
_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # directory junctions and volume mounts


def is_link(path: Path) -> bool:
    """Return whether the path itself redirects elsewhere.

    Covers POSIX and Windows symlinks, plus Windows directory junctions, which
    need no privilege to create and are invisible to ``Path.is_symlink``.
    """

    if path.is_symlink():
        return True
    if sys.platform == "win32":
        try:
            metadata = os.lstat(path)
        except OSError:
            return False
        if metadata.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return metadata.st_reparse_tag in (
                _IO_REPARSE_TAG_SYMLINK,
                _IO_REPARSE_TAG_MOUNT_POINT,
            )
    return False
