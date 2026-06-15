"""T018 — Data-layer path conventions for retro-mester outputs.

Provides:
- Tier path helpers: ``bronze_dir``, ``silver_dir``, ``gold_dir`` following
  ``data/{bronze,silver,gold}/retro-mester/{semester}-{course_slug}/``.
- ``output_key(semester, course_slug) -> str`` — canonical composite key.

Adapted from ``modules/examen/src/examen/output/paths.py`` (T013).
Module name segment is ``retro-mester`` (hyphen, not underscore).
"""

from __future__ import annotations

from pathlib import Path

# Default data root — relative to the project root
_DEFAULT_DATA_ROOT = Path("data")

# Module name as it appears in the path hierarchy
_MODULE_NAME = "retro-mester"


# ---------------------------------------------------------------------------
# Key helper
# ---------------------------------------------------------------------------


def output_key(semester: str, course_slug: str) -> str:
    """Return the canonical composite key for a semester+course pair.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.

    Returns:
        String of the form ``"{semester}-{course_slug}"``.
    """
    return f"{semester}-{course_slug}"


# ---------------------------------------------------------------------------
# Tier path helpers
# ---------------------------------------------------------------------------


def bronze_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/bronze/retro-mester/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Bronze tier directory (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "bronze" / _MODULE_NAME / output_key(semester, course_slug)


def silver_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/silver/retro-mester/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Silver tier directory (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "silver" / _MODULE_NAME / output_key(semester, course_slug)


def gold_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/gold/retro-mester/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Gold tier directory (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "gold" / _MODULE_NAME / output_key(semester, course_slug)


__all__ = [
    "bronze_dir",
    "silver_dir",
    "gold_dir",
    "output_key",
]
