"""Effect size helpers — Cohen's d, η², standardized β, R² (T013).

research §R7 — manual implementation, no pingouin dependency. Reference
equivalence ±1e-6 to scipy/statsmodels native outputs.

Each helper validates inputs at function entry (Fail-Fast) and returns a
plain ``float`` for direct ingestion into Pydantic models.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def cohen_d(group1: Sequence[float] | np.ndarray, group2: Sequence[float] | np.ndarray) -> float:
    """Compute Cohen's d using pooled standard deviation (Cohen 1988 eq. 2.5.1).

    d = (mean1 - mean2) / s_pooled
    where s_pooled = sqrt(((n1-1)·s1² + (n2-1)·s2²) / (n1+n2-2)),
    and s_i is the sample SD with ddof=1.

    Args:
        group1: Numeric values for group 1 (n ≥ 2).
        group2: Numeric values for group 2 (n ≥ 2).

    Returns:
        Cohen's d (signed; positive ⇒ group1 mean larger).

    Raises:
        ValueError: If either group has n < 2 or pooled SD is zero
            (i.e., both groups constant).
    """
    g1 = np.asarray(group1, dtype=float)
    g2 = np.asarray(group2, dtype=float)
    n1, n2 = g1.size, g2.size

    if n1 < 2 or n2 < 2:
        raise ValueError(
            f"cohen_d: each group needs n ≥ 2 (got n1={n1}, n2={n2})"
        )

    s1 = float(g1.std(ddof=1))
    s2 = float(g2.std(ddof=1))
    pooled_var = ((n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2) / (n1 + n2 - 2)
    s_pooled = float(np.sqrt(pooled_var))

    if s_pooled == 0.0:
        raise ValueError(
            "cohen_d: pooled SD is zero — both groups appear constant; "
            "effect size undefined"
        )

    return (float(g1.mean()) - float(g2.mean())) / s_pooled


def eta_squared(ss_between: float, ss_within: float) -> float:
    """Compute η² = SS_between / (SS_between + SS_within).

    Args:
        ss_between: Between-group sum of squares (≥ 0).
        ss_within: Within-group sum of squares (≥ 0).

    Returns:
        η² value in [0, 1].

    Raises:
        ValueError: If either SS is negative or both are zero
            (total SS = 0 ⇒ undefined).
    """
    if ss_between < 0.0 or ss_within < 0.0:
        raise ValueError(
            f"eta_squared: SS values must be non-negative (got "
            f"ss_between={ss_between}, ss_within={ss_within})"
        )
    total = ss_between + ss_within
    if total == 0.0:
        raise ValueError(
            "eta_squared: ss_between + ss_within is zero — η² undefined"
        )
    return ss_between / total


def standardized_beta(coef: float, sd_x: float, sd_y: float) -> float:
    """Compute standardized regression coefficient β* = β · (sd_x / sd_y).

    Both standard deviations must be strictly positive — when sd_x = 0 the
    predictor is constant and the regression coefficient itself is
    undefined upstream (statsmodels would have refused), so silently
    returning 0 here masks a pipeline anomaly. Fail-Fast per
    qa-engineer GAP-9 mitigation 2026-04-30.

    Args:
        coef: Raw regression coefficient.
        sd_x: Standard deviation of the predictor (> 0).
        sd_y: Standard deviation of the outcome (> 0).

    Returns:
        Standardized β.

    Raises:
        ValueError: If either standard deviation is non-positive.
    """
    if sd_x <= 0.0:
        raise ValueError(
            f"standardized_beta: sd_x must be > 0 (got {sd_x}); "
            f"a zero-variance predictor signals an upstream pipeline anomaly"
        )
    if sd_y <= 0.0:
        raise ValueError(f"standardized_beta: sd_y must be > 0 (got {sd_y})")
    return coef * sd_x / sd_y


def r_squared(
    y_true: Sequence[float] | np.ndarray,
    y_pred: Sequence[float] | np.ndarray,
) -> float:
    """Compute the coefficient of determination R² = 1 - SS_res / SS_tot.

    Note R² can be negative when the model performs worse than the mean
    baseline; callers (e.g., regression fit summary V2) should clamp or
    flag this as a pipeline anomaly.

    Args:
        y_true: Observed outcomes (n ≥ 2 with non-zero variance).
        y_pred: Predicted outcomes (same length as y_true).

    Returns:
        R² (≤ 1; can be negative for poor fits).

    Raises:
        ValueError: If lengths differ, or y_true is constant
            (SS_tot = 0 ⇒ undefined).
    """
    y = np.asarray(y_true, dtype=float)
    yh = np.asarray(y_pred, dtype=float)

    if y.shape != yh.shape:
        raise ValueError(
            f"r_squared: y_true/y_pred length mismatch ({y.shape} vs {yh.shape})"
        )

    ss_tot = float(((y - y.mean()) ** 2).sum())
    if ss_tot == 0.0:
        raise ValueError(
            "r_squared: y_true is constant (ss_tot=0) — R² undefined"
        )

    ss_res = float(((y - yh) ** 2).sum())
    return 1.0 - ss_res / ss_tot


__all__ = ["cohen_d", "eta_squared", "standardized_beta", "r_squared"]
