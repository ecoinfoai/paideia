"""T014 — Data-layer path conventions, run_id computation, and atomic writes.

Provides:
- Tier path helpers: ``bronze_dir``, ``silver_dir``, ``gold_dir`` following
  ``data/{bronze,silver,gold}/maieutica/{semester}-{course_slug}/``.
- ``compute_run_id(spec_bytes, curriculum_bytes, chapter_bytes) -> str`` —
  SHA-256 prefix of the concatenated input bytes; 16 hex chars.
- ``atomic_write(path, write_fn)`` — temp→rename pattern; no partial files.
- ``run_gold_dir(...)`` — run-versioned Gold path keyed by ``run_id`` so that
  re-running never overwrites a professor-edited draft.

Output-separation design (FR-020 / SC-012)
------------------------------------------
Gold outputs live under::

    data/gold/maieutica/{semester}-{course_slug}/runs/{run_id}/

``run_id`` is ``sha256(spec_bytes + curriculum_bytes + chapter_bytes)[:16]``.
The base Gold dir is kept for stable named artefacts (e.g. a professor-edited
copy); re-runs write only into the ``runs/{run_id}`` subdirectory.

Example::

    from maieutica.output.paths import gold_dir, run_gold_dir, compute_run_id, atomic_write

    run_id = compute_run_id(spec_bytes, curriculum_bytes, chapter_bytes)
    dest = run_gold_dir("2026-1", "anatomy", run_id=run_id) / "manifest.json"
    atomic_write(dest, lambda p: p.write_text(json.dumps(data)))
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

# Default data root — relative to project root
_DEFAULT_DATA_ROOT = Path("data")


# ---------------------------------------------------------------------------
# Tier path helpers
# ---------------------------------------------------------------------------


def bronze_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/bronze/maieutica/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Bronze tier directory (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "bronze" / "maieutica" / f"{semester}-{course_slug}"


def silver_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/silver/maieutica/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Silver tier directory (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "silver" / "maieutica" / f"{semester}-{course_slug}"


def gold_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/gold/maieutica/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Gold tier directory (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "gold" / "maieutica" / f"{semester}-{course_slug}"


# ---------------------------------------------------------------------------
# run_id computation
# ---------------------------------------------------------------------------


def compute_run_id(
    generation_spec_bytes: bytes,
    curriculum_map_bytes: bytes,
    chapter_txt_bytes: bytes,
) -> str:
    """Compute a deterministic run identifier from the three input byte sequences.

    ``run_id = sha256(spec + curriculum + chapter)[:16]`` — 16 hex characters.

    The same inputs always produce the same run_id (idempotent).  Any change
    to any input produces a different run_id (isolation).

    Args:
        generation_spec_bytes: Raw bytes of the ``generation_spec.yaml`` file.
        curriculum_map_bytes: Raw bytes of the ``curriculum_map.yaml`` file.
        chapter_txt_bytes: Raw bytes of the chapter textbook ``.txt`` file.

    Returns:
        16-character lowercase hex string.

    Raises:
        ValueError: If any input is empty (fail-fast boundary check).
    """
    if not generation_spec_bytes:
        raise ValueError("generation_spec_bytes must not be empty")
    if not curriculum_map_bytes:
        raise ValueError("curriculum_map_bytes must not be empty")
    if not chapter_txt_bytes:
        raise ValueError("chapter_txt_bytes must not be empty")

    digest = hashlib.sha256(
        generation_spec_bytes + curriculum_map_bytes + chapter_txt_bytes
    ).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def atomic_write(path: Path, write_fn: Callable[[Path], None]) -> None:
    """Write a file atomically using a temp-file then ``os.replace``.

    ``write_fn`` is called with a temporary ``Path`` in the same directory
    as ``path``.  On success the temp file is renamed to ``path``
    (``os.replace`` is atomic on POSIX).  On any exception the temp file
    is cleaned up and the exception is re-raised — ``path`` is left
    untouched (constitution V: 부분 산출 금지).

    The temp file is placed in the same directory as ``path`` to guarantee
    the rename is a same-device operation (required for atomicity).

    Args:
        path: Final destination path.  The parent directory must exist.
        write_fn: Callable that receives the temp ``Path`` and writes to it.

    Raises:
        Exception: Any exception raised by ``write_fn`` (after cleanup).
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


# ---------------------------------------------------------------------------
# Output separation — run-versioned Gold path
# ---------------------------------------------------------------------------


def run_gold_dir(
    semester: str,
    course_slug: str,
    *,
    run_id: str,
    data_root: Path | None = None,
) -> Path:
    """Return a run-isolated subdirectory under the Gold tier.

    Artefacts written here are keyed by ``run_id`` so that:

      1. A re-run with the same inputs produces the *same* path (idempotent).
      2. A re-run with different inputs produces a *different* path, leaving
         the previous version intact.
      3. Professors may freely edit files in the base Gold dir without risk
         of them being overwritten by a subsequent run.

    Path convention::

        {data_root}/gold/maieutica/{semester}-{course_slug}/runs/{run_id}/

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        run_id: Opaque run identifier, typically from ``compute_run_id()``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Run-versioned Gold directory path (not necessarily created).
    """
    base = gold_dir(semester, course_slug, data_root=data_root)
    return base / "runs" / run_id


__all__ = [
    "bronze_dir",
    "silver_dir",
    "gold_dir",
    "compute_run_id",
    "atomic_write",
    "run_gold_dir",
]
