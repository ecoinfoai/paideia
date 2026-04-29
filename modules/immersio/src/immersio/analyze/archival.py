"""Atomic archival of immersio's silver + gold outputs (T062, FR-025, R-09).

Mirrors the needs-map ``archive_mover`` 3-step procedure (research §R-09)
but operates over both immersio silver and gold canonical paths in a
single call so the orchestrator (T063) treats archival as one atomic
unit:

    1. For each canonical path that exists with non-archive entries,
       create ``_archive/{ISO8601_UTC}__v{schema_version}/``.
    2. Move every non-archive entry into the new archive subdir
       (``Path.rename`` is atomic on the same filesystem).
    3. Verify the canonical path is empty before the orchestrator writes
       new outputs (FR-025 + Constitution V "부분 산출 금지").

``schema_version`` resolution order (highest → lowest priority):
    1. Explicit ``schema_version`` argument (testing / pinned override).
    2. ``manifest.json::schema_version`` in silver dir.
    3. ``manifest.json::schema_version`` in gold dir.
    4. Fallback ``"unknown"``.

Any failure raises :class:`ArchivalError` so the pipeline aborts BEFORE
new outputs land — no silent partial state. The orchestrator (T063)
maps the exception to CLI exit 4 (FR-033).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import logging

logger = logging.getLogger(__name__)

_ARCHIVE_NAME = "_archive"
_UNKNOWN_SCHEMA_SUFFIX = "unknown"


class ArchivalError(Exception):
    """Raised when archive_previous_run cannot complete atomically."""


def _archive_timestamp() -> str:
    """ISO8601 UTC compact form usable as a directory name (no colons).

    Microseconds appended to avoid collisions on rapid back-to-back
    re-runs (integration tests calling archival twice in one second).
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def _detect_schema_version(*candidates: Path) -> str:
    """Read the first available ``manifest.json::schema_version`` value.

    Returns ``"unknown"`` when no manifest is parseable. Best-effort —
    refusing to archive over a malformed manifest would leave the
    operator unable to re-run.
    """
    for candidate in candidates:
        manifest = candidate / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
        if isinstance(schema_version, str) and schema_version:
            return schema_version
    return _UNKNOWN_SCHEMA_SUFFIX


def _archive_one(direct_path: Path, subdir_name: str) -> str | None:
    """Move every non-archive entry of ``direct_path`` into a fresh archive subdir.

    Args:
        direct_path: Canonical output directory. Returns ``None`` when
            it does not exist or is already empty (no-op).
        subdir_name: Pre-built archive subdir name shared across silver
            + gold so a single timestamp links the pair.

    Returns:
        Relative path string ``"_archive/{subdir_name}"`` on success,
        ``None`` on no-op.
    """
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


def archive_previous_run(
    *,
    silver_dir: Path,
    gold_dir: Path,
    schema_version: str | None = None,
) -> dict[str, str] | None:
    """Move previous-run silver + gold outputs into ``_archive/{ISO}__v{schema}/``.

    Both directories share a single timestamp + schema_version suffix so
    operators inspecting ``_archive/`` after multiple iterations can
    pair the two halves of one analysis run.

    Args:
        silver_dir: Canonical silver output directory (e.g.
            ``data/silver/immersio/2026-1-anatomy``). May not exist on
            the first run.
        gold_dir: Canonical gold output directory (e.g.
            ``data/gold/immersio/2026-1-anatomy``). May not exist on the
            first run.
        schema_version: Optional explicit schema version for the
            archive subdir suffix. When ``None``, falls back to
            ``manifest.json::schema_version`` in silver, then gold,
            then ``"unknown"``.

    Returns:
        ``{"silver": "_archive/{name}", "gold": "_archive/{name}"}`` on
        success; ``None`` when both canonical paths are absent or empty
        (first-run path).

    Raises:
        TypeError: When either path argument is not ``pathlib.Path``.
        ArchivalError: On any partial failure. Caller MUST treat as
            fatal (CLI exit 4 / FR-033).
    """
    if not isinstance(silver_dir, Path):
        raise TypeError(
            f"archive_previous_run: silver_dir must be pathlib.Path, got "
            f"{type(silver_dir).__name__}."
        )
    if not isinstance(gold_dir, Path):
        raise TypeError(
            f"archive_previous_run: gold_dir must be pathlib.Path, got "
            f"{type(gold_dir).__name__}."
        )

    if schema_version is None:
        schema_version = _detect_schema_version(silver_dir, gold_dir)
    elif not isinstance(schema_version, str) or not schema_version:
        raise ArchivalError(
            f"archive_previous_run: schema_version must be a non-empty string, "
            f"got {schema_version!r}."
        )

    timestamp = _archive_timestamp()
    subdir_name = f"{timestamp}__v{schema_version}"

    silver_archive = _archive_one(silver_dir, subdir_name)
    gold_archive = _archive_one(gold_dir, subdir_name)

    if silver_archive is None and gold_archive is None:
        return None

    out: dict[str, str] = {}
    if silver_archive is not None:
        out["silver"] = silver_archive
    if gold_archive is not None:
        out["gold"] = gold_archive

    logger.info(
        "archival: silver=%s gold=%s schema=%s",
        out.get("silver", "(none)"),
        out.get("gold", "(none)"),
        schema_version,
    )
    return out


__all__ = ["ArchivalError", "archive_previous_run"]
