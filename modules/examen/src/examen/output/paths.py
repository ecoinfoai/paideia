"""T013 — Data-layer path conventions, atomic writes, and output separation.

Provides:
- Tier path helpers: ``bronze_dir``, ``silver_dir``, ``gold_dir`` following
  ``data/{bronze,silver,gold}/examen/{semester}-{course_slug}/``.
- ``atomic_write(path, write_fn)`` — temp→rename pattern; no partial files.
- ``run_gold_dir(...)`` — run-versioned Gold path keyed by ``run_id`` so that
  re-running never overwrites a professor-edited draft.

Output-separation design (FR-020 / SC-012)
------------------------------------------
Gold outputs live under::

    data/gold/examen/{semester}-{course_slug}/runs/{run_id}/

``run_id`` is an opaque string (typically a SHA-256 prefix of the input
bundle hash, supplied by the caller).  The base Gold dir
``data/gold/examen/{semester}-{course_slug}/`` is intentionally kept for
stable named artefacts (e.g. a professor-edited copy); re-runs write only
into the ``runs/{run_id}`` subdirectory and never touch the base dir.

Example::

    from examen.output.paths import gold_dir, run_gold_dir, atomic_write

    dest = run_gold_dir("2026-1", "anatomy", run_id="ab12cd34") / "manifest.json"
    atomic_write(dest, lambda p: p.write_text(json.dumps(data)))
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

# 기본 데이터 루트 — 프로젝트 루트 상대 경로
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
    """Return ``{data_root}/bronze/examen/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Bronze tier directory (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "bronze" / "examen" / f"{semester}-{course_slug}"


def silver_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/silver/examen/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Silver tier directory (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "silver" / "examen" / f"{semester}-{course_slug}"


def gold_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/gold/examen/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Gold tier directory (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "gold" / "examen" / f"{semester}-{course_slug}"


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
    # 임시 파일은 목표 디렉터리와 같은 디바이스에 생성해야 rename이 원자적
    parent = path.parent
    tmp_fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=".tmp_")
    tmp_path = Path(tmp_name)
    # mkstemp이 반환한 fd는 즉시 닫는다 — write_fn이 직접 파일을 열어 쓰므로
    os.close(tmp_fd)
    try:
        write_fn(tmp_path)
        os.replace(tmp_path, path)  # POSIX-atomic rename
    except Exception:
        # 실패 시 임시 파일 제거 (부분 산출 방지)
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

    Artefacts written here are keyed by ``run_id`` (typically a SHA-256
    prefix of the input-bundle hash) so that::

      1. A re-run with the same inputs produces the *same* path (idempotent).
      2. A re-run with different inputs (or a new draft) produces a *different*
         path, leaving the previous version intact.
      3. Professors may freely edit files in the base Gold dir without risk of
         them being overwritten by a subsequent run.

    Path convention::

        {data_root}/gold/examen/{semester}-{course_slug}/runs/{run_id}/

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        run_id: Opaque run identifier (input hash prefix or explicit label).
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
    "atomic_write",
    "run_gold_dir",
]
