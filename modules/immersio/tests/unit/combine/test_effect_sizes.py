"""TDD tests for ``combine.effect_sizes`` helpers (T013).

References (research §R7 — manual implementation, no pingouin):
    - Cohen's d (pooled): Cohen, J. (1988). Statistical Power Analysis for
      the Behavioral Sciences (2nd ed.), eq. 2.5.1.
    - η²: Cohen (1973), Levine & Hullett (2002).
    - Standardized β: β* = β · (s_x / s_y).
    - R² = 1 - SS_res / SS_tot (regression definition).

Tolerance ±1e-6 vs hand-computed reference (matches scipy/statsmodels native).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from immersio.combine.effect_sizes import (
    cohen_d,
    eta_squared,
    r_squared,
    standardized_beta,
)

# ----------------------------------------------------------------------
# cohen_d (two-group pooled SD)
# ----------------------------------------------------------------------


def test_cohen_d_known_reference() -> None:
    """Hand-computed reference: g1=[60,62,65,70,72], g2=[75,78,80,82,85]."""
    g1 = [60.0, 62.0, 65.0, 70.0, 72.0]
    g2 = [75.0, 78.0, 80.0, 82.0, 85.0]
    d = cohen_d(g1, g2)
    assert math.isclose(d, -3.1477927995, abs_tol=1e-6)


def test_cohen_d_zero_when_means_equal() -> None:
    g1 = [1.0, 2.0, 3.0]
    g2 = [2.0, 1.0, 3.0]  # same mean different SD → d=0
    assert math.isclose(cohen_d(g1, g2), 0.0, abs_tol=1e-12)


def test_cohen_d_sign_reflects_direction() -> None:
    """Positive d when group1 mean > group2."""
    g1 = [10.0, 11.0, 12.0]
    g2 = [1.0, 2.0, 3.0]
    assert cohen_d(g1, g2) > 0


def test_cohen_d_n_lt_2_each_rejected() -> None:
    """Pooled SD undefined when either n < 2."""
    with pytest.raises(ValueError, match="cohen_d"):
        cohen_d([5.0], [1.0, 2.0, 3.0])


def test_cohen_d_zero_pooled_sd_rejected() -> None:
    """Both groups constant ⇒ pooled SD = 0 ⇒ undefined (Fail-Fast)."""
    with pytest.raises(ValueError, match="pooled"):
        cohen_d([5.0, 5.0, 5.0], [3.0, 3.0, 3.0])


def test_cohen_d_numpy_array_accepted() -> None:
    g1 = np.array([60.0, 62.0, 65.0, 70.0, 72.0])
    g2 = np.array([75.0, 78.0, 80.0, 82.0, 85.0])
    assert math.isclose(cohen_d(g1, g2), -3.1477927995, abs_tol=1e-6)


# ----------------------------------------------------------------------
# eta_squared (between-group / total)
# ----------------------------------------------------------------------


def test_eta_squared_known_reference() -> None:
    assert math.isclose(eta_squared(100.0, 400.0), 0.2, abs_tol=1e-12)


def test_eta_squared_zero_between_yields_zero() -> None:
    assert eta_squared(0.0, 100.0) == 0.0


def test_eta_squared_zero_within_yields_one() -> None:
    """All variance between groups ⇒ η²=1."""
    assert math.isclose(eta_squared(50.0, 0.0), 1.0, abs_tol=1e-12)


def test_eta_squared_negative_ss_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        eta_squared(-1.0, 10.0)


def test_eta_squared_zero_total_rejected() -> None:
    """ss_between=0 AND ss_within=0 ⇒ undefined."""
    with pytest.raises(ValueError, match="zero"):
        eta_squared(0.0, 0.0)


def test_eta_squared_in_unit_interval() -> None:
    for ssb, ssw in [(1.0, 9.0), (2.5, 7.5), (5.0, 5.0)]:
        v = eta_squared(ssb, ssw)
        assert 0.0 <= v <= 1.0


# ----------------------------------------------------------------------
# standardized_beta
# ----------------------------------------------------------------------


def test_standardized_beta_known_reference() -> None:
    assert math.isclose(standardized_beta(1.5, 2.0, 3.0), 1.0, abs_tol=1e-12)


def test_standardized_beta_zero_coef_yields_zero() -> None:
    assert standardized_beta(0.0, 2.0, 3.0) == 0.0


def test_standardized_beta_zero_sd_y_rejected() -> None:
    with pytest.raises(ValueError, match="sd_y"):
        standardized_beta(1.0, 2.0, 0.0)


def test_standardized_beta_negative_sd_x_rejected() -> None:
    with pytest.raises(ValueError, match="sd_x"):
        standardized_beta(1.0, -2.0, 3.0)


def test_standardized_beta_zero_sd_x_rejected() -> None:
    """qa GAP-9 (2026-04-30): sd_x=0 ⇒ predictor constant ⇒ Fail-Fast.

    Silently returning 0 masks a zero-variance column that statsmodels
    upstream should have already rejected; we add a defensive guard so
    the anomaly never reaches the manifest.
    """
    with pytest.raises(ValueError, match="sd_x"):
        standardized_beta(1.0, 0.0, 3.0)


def test_standardized_beta_negative_sd_y_rejected() -> None:
    with pytest.raises(ValueError, match="sd_y"):
        standardized_beta(1.0, 2.0, -3.0)


# ----------------------------------------------------------------------
# r_squared (regression goodness-of-fit)
# ----------------------------------------------------------------------


def test_r_squared_known_reference() -> None:
    """Hand-computed: y_true=[1..5], y_pred=[1.1, 1.9, 3.2, 3.8, 5.1] → R²=0.989."""
    y_true = [1.0, 2.0, 3.0, 4.0, 5.0]
    y_pred = [1.1, 1.9, 3.2, 3.8, 5.1]
    assert math.isclose(r_squared(y_true, y_pred), 0.989, abs_tol=1e-6)


def test_r_squared_perfect_fit_yields_one() -> None:
    y = [1.0, 2.0, 3.0, 4.0]
    assert math.isclose(r_squared(y, y), 1.0, abs_tol=1e-12)


def test_r_squared_constant_y_true_rejected() -> None:
    """SS_total = 0 ⇒ R² undefined."""
    with pytest.raises(ValueError, match="constant"):
        r_squared([5.0, 5.0, 5.0], [4.0, 5.0, 6.0])


def test_r_squared_length_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="length"):
        r_squared([1.0, 2.0], [1.0])


def test_r_squared_can_be_negative_when_pred_worse_than_mean() -> None:
    """R² is bounded above by 1 but can be negative when y_pred worse than mean."""
    y_true = [1.0, 2.0, 3.0]
    y_pred = [10.0, 10.0, 10.0]
    r2 = r_squared(y_true, y_pred)
    assert r2 < 0


def test_r_squared_numpy_input_accepted() -> None:
    y_true = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y_pred = np.array([1.1, 1.9, 3.2, 3.8, 5.1])
    assert math.isclose(r_squared(y_true, y_pred), 0.989, abs_tol=1e-6)
