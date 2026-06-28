"""Owner-only atomic file writer for PII-bearing artifacts.

Centralizes the temp-file → ``os.replace`` write pattern used across paideia
modules (security findings DAR-01/DAR-02).  Two guarantees beyond the plain
metric-codex helper:

- **Owner-only permissions** — the final file always has ``mode & 0o077 == 0``
  (no group/other bits), regardless of the process umask.  ``mkstemp`` creates
  the temp file ``0o600``, but an explicit ``os.chmod`` is re-applied *after*
  ``write_fn`` returns so the guarantee survives a ``write_fn`` that unlinked
  and recreated the file with looser permissions.
- **Atomicity** — on any exception from ``write_fn`` the temp file is removed
  and the exception re-raised; ``path`` is never partially written
  (constitution V).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

_OWNER_ONLY = 0o600


def atomic_write(path: Path, write_fn: Callable[[Path], None]) -> None:
    """Write a file atomically with owner-only permissions.

    A temp file is created in ``path``'s parent directory (same device, so the
    rename is atomic on POSIX) and passed to ``write_fn``.  After ``write_fn``
    returns, the temp file is forced to mode ``0o600`` and renamed onto
    ``path`` via ``os.replace``.  On any exception the temp file is removed and
    the exception re-raised, leaving ``path`` untouched.

    Args:
        path: Final destination path. The parent directory must already exist.
        write_fn: Callable that receives the temp ``Path`` and writes the
            intended content to it.

    Raises:
        Exception: Any exception raised by ``write_fn`` (after temp cleanup).
    """
    parent = path.parent
    tmp_fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=".tmp_")
    tmp_path = Path(tmp_name)
    # write_fn opens the file itself; close the descriptor mkstemp handed us.
    os.close(tmp_fd)
    try:
        write_fn(tmp_path)
        # Re-assert owner-only perms in case write_fn recreated the file with
        # a different (umask-derived) mode; mkstemp's 0o600 alone is not enough.
        os.chmod(tmp_path, _OWNER_ONLY)
        os.replace(tmp_path, path)  # POSIX-atomic rename
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


__all__ = ["atomic_write"]
