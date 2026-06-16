"""BH-FDR adjustment helper — wraps ``scipy.stats.false_discovery_control`` (T012).

FR-007 — Benjamini-Hochberg q=0.05 single policy. research §R4 — scipy 1.11+
direct call (no manual implementation). Order of inputs is preserved so that
callers (correlation, regression, subgroup_compare) can map q-values back by
the same index used for raw p-values.

References:
    Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery
    rate: a practical and powerful approach to multiple testing. JRSS B,
    57(1), 289-300.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from scipy.stats import false_discovery_control


def bh_fdr_adjust(p_values: Iterable[float]) -> list[float]:
    """Adjust raw p-values via the Benjamini-Hochberg FDR procedure.

    The output preserves the input ordering (q[i] corresponds to p[i])
    and is clamped to [0, 1]. Tied p-values yield identical q-values
    via scipy's stable sort, which is required for byte-identical
    re-runs (determinism vector 7).

    Args:
        p_values: One-dimensional iterable of raw p-values, each in
            [0, 1]. Empty input is rejected (Fail-Fast).

    Returns:
        List of BH-adjusted q-values in the same order as the input.

    Raises:
        ValueError: If the input is empty, or any p-value is outside
            [0, 1] or is NaN.
    """
    arr = np.asarray(list(p_values), dtype=float)

    if arr.size == 0:
        raise ValueError("bh_fdr_adjust: empty p-value vector rejected")

    if np.isnan(arr).any():
        raise ValueError("bh_fdr_adjust: p-value contains NaN")

    if (arr < 0.0).any() or (arr > 1.0).any():
        raise ValueError(
            f"bh_fdr_adjust: p-value outside [0, 1] (got min={arr.min()}, max={arr.max()})"
        )

    q = false_discovery_control(arr, method="bh")
    # Clamp into [0, 1] defensively (scipy already does this, but explicit
    # for downstream Pydantic V2 q-range validators).
    q = np.clip(q, 0.0, 1.0)
    return [float(qi) for qi in q]


__all__ = ["bh_fdr_adjust"]
