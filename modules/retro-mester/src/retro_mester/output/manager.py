"""T019 — Output management: archival and atomic writes.

Provides:
- ``archive_existing(target_dir, when)`` — move current outputs into
  ``target_dir/_archive/{ISO8601(when)}/`` before a fresh run.  Returns
  the archive path on success, ``None`` when the directory is absent or empty.
- ``atomic_write_bytes(path, data)`` / ``atomic_write_text(path, text)`` —
  write via temp file + ``os.replace`` so partial outputs never appear.
- ``_atomic_write(path, write_fn)`` — lower-level helper exposed for testing.

Design notes:
- ``archive_existing`` takes an explicit ``when: datetime`` parameter to keep
  outputs reproducible and testable (callers pass a fixed datetime in tests).
- The archive subdirectory name is the ISO-8601 UTC form of ``when`` with
  colons replaced by nothing (standard Z-suffix form: ``YYYY-MM-DDTHH:MM:SSZ``).
  This is human-readable and sortable.
- Atomic rename is POSIX-atomic on the same filesystem (``os.replace``).
  The temp file is placed in the same directory as the destination to guarantee
  the same-device requirement.
"""

from __future__ import annotations

import contextlib
import datetime
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

_ARCHIVE_DIR_NAME = "_archive"


# ---------------------------------------------------------------------------
# Archival
# ---------------------------------------------------------------------------


def archive_existing(target_dir: Path, when: datetime.datetime) -> Path | None:
    """Move existing direct-path outputs into ``target_dir/_archive/{iso}/``.

    Only non-archive entries (i.e. everything except the ``_archive``
    subdirectory itself) are moved.  The ``_archive`` dir is left in place.

    Args:
        target_dir: The output directory whose contents to archive.
        when: Timestamp used to name the archive subdirectory.

    Returns:
        Absolute path of the created archive subdirectory on success, or
        ``None`` when ``target_dir`` is absent or contains no archivable entries.
    """
    if not target_dir.exists():
        return None
    if not target_dir.is_dir():
        raise ValueError(
            f"archive_existing: target_dir is not a directory: {target_dir}"
        )

    entries = [p for p in target_dir.iterdir() if p.name != _ARCHIVE_DIR_NAME]
    if not entries:
        return None

    iso = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    archive_subdir = target_dir / _ARCHIVE_DIR_NAME / iso
    archive_subdir.mkdir(parents=True, exist_ok=False)

    for entry in entries:
        entry.rename(archive_subdir / entry.name)

    return archive_subdir


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, write_fn: Callable[[Path], None]) -> None:
    """Write a file atomically using a temp file then ``os.replace``.

    ``write_fn`` is called with a temporary ``Path`` in the same directory
    as ``path``.  On success the temp file is renamed to ``path``
    (``os.replace`` is atomic on POSIX).  On any exception the temp file
    is cleaned up and the exception is re-raised — ``path`` is never
    left in a partial state.

    Args:
        path: Final destination path.  The parent directory must exist.
        write_fn: Callable that receives the temp ``Path`` and writes to it.

    Raises:
        Exception: Any exception raised by ``write_fn`` (after temp cleanup).
    """
    parent = path.parent
    tmp_fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=".tmp_")
    tmp_path = Path(tmp_name)
    # Close the fd immediately — write_fn opens the file itself
    os.close(tmp_fd)
    try:
        write_fn(tmp_path)
        os.replace(tmp_path, path)  # POSIX-atomic rename
    except Exception:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically.

    Uses a temp-file + rename pattern so ``path`` is never observed in a
    partial state by concurrent readers.

    Args:
        path: Destination file path.  Parent directory must exist.
        data: Raw bytes to write.
    """
    _atomic_write(path, lambda p: p.write_bytes(data))


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically.

    Uses a temp-file + rename pattern so ``path`` is never observed in a
    partial state by concurrent readers.

    Args:
        path: Destination file path.  Parent directory must exist.
        text: Text content to write.
        encoding: File encoding (default ``"utf-8"``).
    """
    _atomic_write(path, lambda p: p.write_text(text, encoding=encoding))


__all__ = [
    "archive_existing",
    "atomic_write_bytes",
    "atomic_write_text",
    "_atomic_write",
]
