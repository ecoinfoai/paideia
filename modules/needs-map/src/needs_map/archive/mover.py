"""Atomic archival of previous-run outputs (T023, FR-002 / FR-002a; T063 v0.1.1).

Implements research D7's 3-step procedure:
    1. Ensure ``_archive/{ISO8601_UTC}__v{schema_version}/`` exists.
    2. Move every entry under the direct path into the new archive subdir.
    3. Verify the direct path is empty before the caller writes new outputs.

The ``__v{schema_version}`` suffix on the archive subdir name (research §R-09)
lets an operator inspecting ``_archive/`` after multiple iterations classify
which archived runs belong to which schema generation (e.g. v0.1.0 = ``1.0.0``,
v0.1.1 = ``1.1.0``). The suffix is parsed off the prior ``manifest.json`` —
when the manifest is missing or unparseable the fallback suffix ``unknown`` is
used so archival still succeeds rather than blocking the pipeline (FR-002a
"archival never blocks new outputs on best-effort metadata").

POSIX ``Path.rename`` is atomic on the same filesystem, so partial moves do not
occur. Any failure raises :class:`ArchivalError` so the pipeline aborts BEFORE
new outputs land — no silent partial state (adversary H-7).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class ArchivalError(Exception):
    """Raised when archive_previous_run cannot complete atomically."""


_ARCHIVE_NAME = "_archive"
_UNKNOWN_SCHEMA_SUFFIX = "unknown"


def _archive_timestamp() -> str:
    """ISO8601 UTC compact form usable as a directory name (no colons).

    Microseconds are appended (``%fZ``) to avoid collisions on rapid back-to-back
    re-runs (e.g. integration tests that call the pipeline twice in one second).
    The wall-clock second is still recoverable from the leading 19 characters.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def _detect_prior_schema_version(direct_path: Path) -> str:
    """Read the prior ``manifest.json``'s ``schema_version`` for the suffix.

    Returns ``"unknown"`` rather than raising when the manifest is missing
    or its schema_version field is absent / non-string. Archival is a
    best-effort classification step — refusing to archive because of a
    malformed prior manifest would leave the operator unable to re-run.
    """
    manifest_path = direct_path / "manifest.json"
    if not manifest_path.is_file():
        return _UNKNOWN_SCHEMA_SUFFIX
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _UNKNOWN_SCHEMA_SUFFIX
    schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
    if not isinstance(schema_version, str) or not schema_version:
        return _UNKNOWN_SCHEMA_SUFFIX
    return schema_version


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
            f"archive_previous_run: expected pathlib.Path, got {type(direct_path).__name__}."
        )

    if not direct_path.exists():
        return None

    if not direct_path.is_dir():
        raise ArchivalError(f"archive_previous_run: direct_path is not a directory: {direct_path}")

    entries = [p for p in direct_path.iterdir() if p.name != _ARCHIVE_NAME]
    if not entries:
        return None

    archive_root = direct_path / _ARCHIVE_NAME
    timestamp = _archive_timestamp()
    schema_suffix = _detect_prior_schema_version(direct_path)
    subdir_name = f"{timestamp}__v{schema_suffix}"
    target_dir = archive_root / subdir_name

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

    return f"{_ARCHIVE_NAME}/{subdir_name}"
