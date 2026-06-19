"""T016 — Data-layer path conventions for metric-codex.

Provides tier path helpers following::

    data/{bronze,silver,gold}/metric-codex/{semester}-{course_slug}/

and a run-versioned Gold helper for output isolation (re-runs never
overwrite a previously written artefact set).

Note: ``atomic_write`` lives in ``metric_codex.output.determinism``, not here.
This module is path conventions only.

Example::

    from metric_codex.output.paths import gold_dir, run_gold_dir

    dest = run_gold_dir("2026-1", "anatomy", run_id="ab12cd34") / "manifest.json"
"""

from __future__ import annotations

from pathlib import Path

# Default data root — relative to the project working directory.
_DEFAULT_DATA_ROOT = Path("data")

# Tier name used in every path; must match the module spec (013-metric-codex).
_TIER_NAME = "metric-codex"


# ---------------------------------------------------------------------------
# Tier path helpers
# ---------------------------------------------------------------------------


def bronze_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/bronze/metric-codex/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Bronze tier directory path (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "bronze" / _TIER_NAME / f"{semester}-{course_slug}"


def silver_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/silver/metric-codex/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Silver tier directory path (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "silver" / _TIER_NAME / f"{semester}-{course_slug}"


def gold_dir(
    semester: str,
    course_slug: str,
    *,
    data_root: Path | None = None,
) -> Path:
    """Return ``{data_root}/gold/metric-codex/{semester}-{course_slug}/``.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        data_root: Override for the ``data/`` root.  Defaults to ``data/``.

    Returns:
        Gold tier directory path (not necessarily created).
    """
    root = data_root if data_root is not None else _DEFAULT_DATA_ROOT
    return root / "gold" / _TIER_NAME / f"{semester}-{course_slug}"


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

    Path convention::

        {data_root}/gold/metric-codex/{semester}-{course_slug}/runs/{run_id}/

    Two calls with the same ``run_id`` return the same path (idempotent).
    Different ``run_id``s yield different paths so re-runs never overwrite
    previous artefacts.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course slug, e.g. ``"anatomy"``.
        run_id: Opaque run identifier (e.g. SHA-256 prefix of input-bundle hash).
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
    "run_gold_dir",
]
