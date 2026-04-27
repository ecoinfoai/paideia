"""Atomic archival of previous-run outputs (T023, FR-002 / FR-002a).

Implements research D7's 3-step procedure:
    1. Ensure ``_archive/{ISO8601_UTC}/`` exists.
    2. Move every entry under the direct path into the new archive subdir.
    3. Verify the direct path is empty before the caller writes new outputs.

POSIX ``Path.rename`` is atomic on the same filesystem, so partial moves do not
occur. Any failure raises :class:`ArchivalError` so the pipeline aborts BEFORE
new outputs land — no silent partial state (adversary H-7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


class ArchivalError(Exception):
    """Raised when archive_previous_run cannot complete atomically."""


_ARCHIVE_NAME = "_archive"


def _archive_timestamp() -> str:
    """ISO8601 UTC compact form usable as a directory name (no colons)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def archive_previous_run(direct_path: Path) -> str | None:
    """Move every direct-path entry into ``_archive/{ISO8601_UTC}/``.

    Args:
        direct_path: The output directory whose previous-run contents must be
            preserved before new outputs are written. May not exist on the
            first run (returns None).

    Returns:
        The relative path of the newly created archive subdir
        (``"_archive/{ISO8601_UTC}"``) on success, or ``None`` if ``direct_path``
        did not exist or was already empty.

    Raises:
        TypeError: If ``direct_path`` is not a :class:`pathlib.Path`.
        ArchivalError: On any partial failure (rename failure, post-move
            non-empty direct path, or unexpected I/O error). Caller MUST treat
            this as fatal and skip output writing.
    """
    if not isinstance(direct_path, Path):
        raise TypeError(
            f"archive_previous_run: expected pathlib.Path, got "
            f"{type(direct_path).__name__}."
        )

    if not direct_path.exists():
        return None

    if not direct_path.is_dir():
        raise ArchivalError(
            f"archive_previous_run: direct_path is not a directory: {direct_path}"
        )

    entries = [p for p in direct_path.iterdir() if p.name != _ARCHIVE_NAME]
    if not entries:
        return None

    archive_root = direct_path / _ARCHIVE_NAME
    timestamp = _archive_timestamp()
    target_dir = archive_root / timestamp

    try:
        target_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ArchivalError(
            f"archive_previous_run: archive subdir already exists "
            f"(timestamp collision): {target_dir}"
        ) from exc
    except OSError as exc:
        raise ArchivalError(
            f"archive_previous_run: cannot create archive subdir {target_dir}: {exc}"
        ) from exc

    for entry in entries:
        destination = target_dir / entry.name
        try:
            entry.rename(destination)
        except OSError as exc:
            raise ArchivalError(
                f"archive_previous_run: failed to move {entry} → {destination}: {exc}"
            ) from exc

    remaining = [p for p in direct_path.iterdir() if p.name != _ARCHIVE_NAME]
    if remaining:
        raise ArchivalError(
            f"archive_previous_run: direct_path not emptied after archival: "
            f"{[p.name for p in remaining]}"
        )

    return f"{_ARCHIVE_NAME}/{timestamp}"
