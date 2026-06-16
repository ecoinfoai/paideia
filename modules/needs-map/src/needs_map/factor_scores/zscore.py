"""Population z-score (T055, FR-008).

ddof=0 (population std), NaN-skip on the mean/std calculation but NaN positions
preserved in the output. Constant column → all zeros (adversary H-2 mitigation:
no ZeroDivisionError, no silent NaN). All-NaN column → all NaN.
"""

from __future__ import annotations

import pandas as pd


def zscore(values: pd.Series) -> pd.Series:
    """Population z-score with NaN-preserving semantics.

    Args:
        values: Per-student axis values. Index preserved on output.

    Returns:
        Z-score Series. Substantive rows: ``(x - mean) / std`` with
        ``ddof=0`` and means/stds computed over substantive rows only. NaN
        positions in the input remain NaN in the output. Constant column:
        all zeros. All-NaN column: all NaN.
    """
    if not isinstance(values, pd.Series):
        raise TypeError(f"zscore: expected pd.Series, got {type(values).__name__}.")

    substantive = values.dropna()
    if substantive.empty:
        return values.copy()

    mean = float(substantive.mean())
    std = float(substantive.std(ddof=0))

    if std == 0.0:
        # Constant column — preserve NaN positions but set substantive rows to 0.
        result = pd.Series(0.0, index=values.index, dtype=float)
        result[values.isna()] = float("nan")
        return result

    return (values - mean) / std
