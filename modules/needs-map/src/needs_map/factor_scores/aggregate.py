"""Axis aggregation (T053, FR-006).

Deterministic mean (likert) or sum (multiselect one-hot) over the long-form
diagnostic_response DataFrame. Returns a per-student :class:`pd.Series` whose
index is the canonical 10-digit student id sorted ascending. Missing items
propagate as NaN — the missing-policy stage (T054) decides drop vs mean_impute.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

AggregateKind = Literal["mean", "sum"]


def aggregate_axis(
    diag_df: pd.DataFrame, axis_columns: list[str], kind: AggregateKind
) -> pd.Series:
    """Aggregate per-student values for one axis.

    Args:
        diag_df: Long-form diagnostic_response DataFrame with columns
            ``student_id, axis, axis_kind, value_int, value_bool, source_column``
            (plus other DiagnosticResponse fields, ignored here).
        axis_columns: Subset of ``source_column`` values that contribute to this
            axis. Order is preserved when pivoting so determinism downstream
            holds (R3 KMeans seed + sorted student_id).
        kind: ``"mean"`` for likert items or ``"sum"`` for multiselect one-hot
            (FR-006). Other values raise ``ValueError``.

    Returns:
        Series indexed by canonical student_id (sorted ascending) with one
        aggregated float value per student. NaN propagates when *any* item
        of a likert axis is missing for that student (drop policy default).

    Raises:
        ValueError: If ``kind`` is not in {"mean", "sum"} or if no rows match
            ``axis_columns``.
    """
    if kind not in ("mean", "sum"):
        raise ValueError(
            f"aggregate_axis: kind={kind!r} not in {{'mean', 'sum'}} (FR-006)."
        )
    if not axis_columns:
        raise ValueError("aggregate_axis: axis_columns must be non-empty.")

    subset = diag_df[diag_df["source_column"].isin(axis_columns)]
    if subset.empty:
        return pd.Series(dtype=float, name="aggregate")

    if kind == "mean":
        # likert items: pivot to wide, then mean across columns. NaN propagates.
        pivot = subset.pivot_table(
            index="student_id",
            columns="source_column",
            values="value_int",
            aggfunc="first",
        )
        pivot = pivot.reindex(columns=axis_columns)
        result = pivot.mean(axis=1, skipna=False)
    else:
        # multiselect one-hot: sum True bools per student across all options of
        # the axis_columns sources.
        coerced = subset.copy()
        coerced["_int_value"] = coerced["value_bool"].astype("Int64").astype("Float64")
        result = coerced.groupby("student_id")["_int_value"].sum(min_count=1)

    result = result.sort_index()
    result.name = "aggregate"
    return result
