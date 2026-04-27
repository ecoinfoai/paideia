"""Per-axis distribution stats for the group report (T097, FR-017 (a))."""

from __future__ import annotations

import pandas as pd

_AXES: tuple[str, ...] = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def compute_axis_distributions(factor_scores_df: pd.DataFrame) -> dict[str, dict]:
    """Histogram bins + summary stats per standard axis.

    Args:
        factor_scores_df: factor_scores.parquet content. Skipped axes
            (all-NaN columns) come back with ``empty=True``.

    Returns:
        ``{axis_name: {mean, std, p25, p50, p75, min, max, n, empty}}`` for
        every axis present in the input. Histogram bin counts deferred to
        the PDF writer (matplotlib) to keep this function lightweight.
    """
    out: dict[str, dict] = {}
    for axis in _AXES:
        if axis not in factor_scores_df.columns:
            out[axis] = {"empty": True, "n": 0}
            continue
        substantive = factor_scores_df[axis].dropna()
        if substantive.empty:
            out[axis] = {"empty": True, "n": 0}
            continue
        out[axis] = {
            "empty": False,
            "n": int(substantive.shape[0]),
            "mean": float(substantive.mean()),
            "std": float(substantive.std(ddof=0)),
            "min": float(substantive.min()),
            "p25": float(substantive.quantile(0.25)),
            "p50": float(substantive.quantile(0.50)),
            "p75": float(substantive.quantile(0.75)),
            "max": float(substantive.max()),
        }
    return out
