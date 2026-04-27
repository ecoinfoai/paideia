"""Cronbach α (T052, FR-004 / FR-005, research D1).

Pure scipy/numpy implementation — see research D1 for the (k/(k-1))(1 - Σvar(item)/var(sum))
formula. ``compute_reliability`` walks the mapping's likert columns per declared
standard axis, builds the per-axis item matrix, and packages a
:class:`ScaleReliabilityReport` that the pipeline writes alongside the parquet
output.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from paideia_shared.schemas import (
    DiagnosticMappingConfig,
    ScaleReliabilityReport,
    ScaleReliabilityRow,
    StandardAxisKey,
)

_OPERATIONAL_WARNING_THRESHOLD = 0.7
_MODULE_VERSION = "needs-map/0.1.0"


def cronbach_alpha(item_matrix: np.ndarray) -> float | None:
    """Compute Cronbach α for an n_responders × k_items numeric matrix.

    Args:
        item_matrix: ``shape=(n_responders, k_items)`` real-valued matrix
            (Likert int responses cast to float). NaN cells short-circuit the
            row from the variance calculation; rows with any NaN are dropped
            *before* variances are computed.

    Returns:
        α value when ``k_items >= 3`` AND total variance is positive, else
        ``None``. NaN-only or all-constant inputs return ``None`` (defensive
        — total variance == 0 makes α undefined).
    """
    if not isinstance(item_matrix, np.ndarray):
        raise TypeError(
            f"cronbach_alpha: expected np.ndarray, got {type(item_matrix).__name__}."
        )
    if item_matrix.ndim != 2:
        raise ValueError(
            f"cronbach_alpha: expected 2-D matrix, got ndim={item_matrix.ndim}."
        )
    n_rows, k_items = item_matrix.shape
    if k_items < 3:
        return None
    # Drop rows containing any NaN (drop policy upstream feeds clean rows here).
    mask = ~np.isnan(item_matrix).any(axis=1)
    clean = item_matrix[mask]
    if clean.shape[0] < 2:
        return None
    item_var_sum = clean.var(axis=0, ddof=1).sum()
    total_var = clean.sum(axis=1).var(ddof=1)
    if total_var <= 0 or not math.isfinite(total_var):
        return None
    alpha = (k_items / (k_items - 1)) * (1.0 - item_var_sum / total_var)
    return float(alpha)


def _likert_columns_for_axis(
    mapping: DiagnosticMappingConfig, axis_key: str
) -> list[str]:
    return [c.source for c in mapping.columns if c.kind == "likert" and c.axis == axis_key]


def _pivot_likert_axis(
    diag_df: pd.DataFrame, axis_key: str, source_columns: list[str]
) -> np.ndarray:
    """Build an n_responders × k_items numeric matrix for one axis from the long-form df."""
    if diag_df.empty or not source_columns:
        return np.empty((0, len(source_columns)), dtype=float)
    subset = diag_df[
        (diag_df["axis"] == axis_key)
        & (diag_df["axis_kind"] == "likert")
        & (diag_df["source_column"].isin(source_columns))
    ]
    if subset.empty:
        return np.empty((0, len(source_columns)), dtype=float)
    pivot = subset.pivot_table(
        index="student_id",
        columns="source_column",
        values="value_int",
        aggfunc="first",
    )
    # Ensure consistent column order (mapping order, not pandas alphabetical)
    pivot = pivot.reindex(columns=source_columns)
    return pivot.to_numpy(dtype=float)


def compute_reliability(
    diag_df: pd.DataFrame, mapping: DiagnosticMappingConfig
) -> ScaleReliabilityReport:
    """Compute α + label per declared standard axis.

    Returns Pydantic-validated :class:`ScaleReliabilityReport`. One row per
    declared axis (``required ∪ optional``).

    For each axis:
      * 0 likert items mapped → label='no_items', alpha=None.
      * 1 or 2 likert items → label='single_item', alpha=None.
      * ≥ 3 likert items → label='computed' if α finite (with operational_warning
        when α < 0.7); else label='not_applicable'.
    """
    declared_axes = list(dict.fromkeys(mapping.axes.required + mapping.axes.optional))
    rows: list[ScaleReliabilityRow] = []
    for axis_key in declared_axes:
        sources = _likert_columns_for_axis(mapping, axis_key)
        if len(sources) == 0:
            rows.append(
                ScaleReliabilityRow(
                    axis_key=axis_key,  # type: ignore[arg-type]
                    n_items=0,
                    cronbach_alpha=None,
                    label="no_items",
                    operational_warning=False,
                )
            )
            continue
        if len(sources) < 3:
            rows.append(
                ScaleReliabilityRow(
                    axis_key=axis_key,  # type: ignore[arg-type]
                    n_items=len(sources),
                    cronbach_alpha=None,
                    label="single_item",
                    operational_warning=False,
                )
            )
            continue
        matrix = _pivot_likert_axis(diag_df, axis_key, sources)
        alpha = cronbach_alpha(matrix)
        if alpha is None:
            rows.append(
                ScaleReliabilityRow(
                    axis_key=axis_key,  # type: ignore[arg-type]
                    n_items=len(sources),
                    cronbach_alpha=None,
                    label="not_applicable",
                    operational_warning=False,
                )
            )
        else:
            warning = alpha < _OPERATIONAL_WARNING_THRESHOLD
            rows.append(
                ScaleReliabilityRow(
                    axis_key=axis_key,  # type: ignore[arg-type]
                    n_items=len(sources),
                    cronbach_alpha=alpha,
                    label="computed",
                    operational_warning=warning,
                )
            )
    return ScaleReliabilityReport(
        rows=rows,
        semester=mapping.metadata.semester,
        course_slug=mapping.metadata.course_slug,
        module_version=_MODULE_VERSION,
    )


# Public type alias for callers that want to import the standard axis vocabulary
# alongside the reliability functions without reaching back into paideia_shared.
__all__ = ["cronbach_alpha", "compute_reliability", "StandardAxisKey"]
