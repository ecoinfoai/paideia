"""TDD tests for ``combine.regression`` (T024, US1).

Verifies the OLS multiple regression of ``total_score ~ 8 z-axes`` plus
VIF + BH-FDR adjusted p-values. Reference equivalence ±1e-4 vs
``statsmodels.api.OLS`` and ``variance_inflation_factor`` native outputs.

GAP-9 mitigation B (qa-engineer 2026-04-30): the regression caller layer
must reject zero-variance predictors *before* statsmodels would silently
collapse the design matrix. We test for ``ValueError`` on a constant
``{axis}_z`` column.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

from immersio.combine.regression import compute_ols_regression
from paideia_shared.schemas import RegressionCoefficient, RegressionFitSummary
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS


def _synthetic_complete_case(n: int, seed: int = 0) -> pd.DataFrame:
    """Build a complete-case dataframe (no missing axis_z, no missing exam)."""
    rng = np.random.default_rng(seed)
    cols: dict[str, object] = {
        "student_id": [f"2026{i:06d}" for i in range(n)],
        "exam_taken": [True] * n,
    }
    # 8 axis_z i.i.d. N(0, 1); total_score = 70 + 5*motivation + N(0, 5).
    for axis in STANDARD_AXIS_KEYS:
        cols[f"{axis}_z"] = rng.normal(0, 1, n).tolist()
    motivation_z = np.array(cols["motivation_z"])
    cols["total_score"] = (70 + 5 * motivation_z + rng.normal(0, 5, n)).tolist()
    return pd.DataFrame(cols)


# ----------------------------------------------------------------------
# Smoke
# ----------------------------------------------------------------------


def test_returns_coefs_and_fit() -> None:
    df = _synthetic_complete_case(n=80)
    coefs, fit = compute_ols_regression(df)
    assert isinstance(coefs, list)
    assert all(isinstance(c, RegressionCoefficient) for c in coefs)
    assert isinstance(fit, RegressionFitSummary)


def test_emits_one_coef_per_axis_in_order() -> None:
    df = _synthetic_complete_case(n=80)
    coefs, _ = compute_ols_regression(df)
    assert [c.axis_key for c in coefs] == list(STANDARD_AXIS_KEYS)


# ----------------------------------------------------------------------
# Reference equivalence ±1e-4
# ----------------------------------------------------------------------


def test_coef_p_ci_matches_statsmodels_reference() -> None:
    df = _synthetic_complete_case(n=120, seed=42)
    coefs, _ = compute_ols_regression(df)

    X = df[[f"{axis}_z" for axis in STANDARD_AXIS_KEYS]]
    y = df["total_score"]
    model = sm.OLS(y, sm.add_constant(X)).fit()

    for cell in coefs:
        sm_coef = float(model.params[f"{cell.axis_key}_z"])
        sm_p = float(model.pvalues[f"{cell.axis_key}_z"])
        sm_ci = model.conf_int().loc[f"{cell.axis_key}_z"]
        assert math.isclose(cell.coef, sm_coef, abs_tol=1e-4)
        assert math.isclose(cell.raw_p, sm_p, abs_tol=1e-4)
        assert math.isclose(cell.ci_low_95, float(sm_ci[0]), abs_tol=1e-4)
        assert math.isclose(cell.ci_high_95, float(sm_ci[1]), abs_tol=1e-4)


def test_r2_and_fstat_match_statsmodels() -> None:
    df = _synthetic_complete_case(n=120, seed=42)
    _, fit = compute_ols_regression(df)
    X = df[[f"{axis}_z" for axis in STANDARD_AXIS_KEYS]]
    y = df["total_score"]
    model = sm.OLS(y, sm.add_constant(X)).fit()
    assert math.isclose(fit.r2, float(model.rsquared), abs_tol=1e-4)
    assert math.isclose(fit.r2_adj, float(model.rsquared_adj), abs_tol=1e-4)
    assert math.isclose(fit.f_stat, float(model.fvalue), abs_tol=1e-4)
    assert math.isclose(fit.f_pvalue, float(model.f_pvalue), abs_tol=1e-4)


def test_vif_matches_statsmodels_reference() -> None:
    df = _synthetic_complete_case(n=120, seed=11)
    coefs, _ = compute_ols_regression(df)
    X = df[[f"{axis}_z" for axis in STANDARD_AXIS_KEYS]].to_numpy()
    X_with_const = sm.add_constant(X)
    for i, cell in enumerate(coefs):
        # axis_i corresponds to column i+1 in the const-prefixed design.
        sm_vif = float(variance_inflation_factor(X_with_const, i + 1))
        assert math.isclose(cell.vif, sm_vif, abs_tol=1e-4)


# ----------------------------------------------------------------------
# Complete-case n + dropout
# ----------------------------------------------------------------------


def test_n_complete_case_dropouts_missing_axes() -> None:
    df = _synthetic_complete_case(n=50)
    df.loc[0:4, "motivation_z"] = None  # 5 students drop
    _, fit = compute_ols_regression(df)
    assert fit.n_complete_case == 45
    assert fit.n_dropped == 5


def test_n_complete_case_dropouts_missing_exam() -> None:
    df = _synthetic_complete_case(n=50)
    df.loc[0:9, "exam_taken"] = False
    df.loc[0:9, "total_score"] = None
    _, fit = compute_ols_regression(df)
    assert fit.n_complete_case == 40


def test_small_sample_warning_below_30() -> None:
    df = _synthetic_complete_case(n=25)
    _, fit = compute_ols_regression(df)
    assert fit.small_sample_warning is True


def test_no_small_sample_warning_at_30() -> None:
    df = _synthetic_complete_case(n=30)
    _, fit = compute_ols_regression(df)
    assert fit.small_sample_warning is False


# ----------------------------------------------------------------------
# BH-FDR consistency on 8 raw_p
# ----------------------------------------------------------------------


def test_fdr_q_matches_scipy() -> None:
    from scipy.stats import false_discovery_control

    df = _synthetic_complete_case(n=120, seed=3)
    coefs, _ = compute_ols_regression(df)
    raw_ps = [c.raw_p for c in coefs]
    expected_q = false_discovery_control(np.asarray(raw_ps), method="bh")
    for cell, q in zip(coefs, expected_q):
        assert math.isclose(cell.fdr_q, float(q), abs_tol=1e-6)


# ----------------------------------------------------------------------
# Multicollinearity flag
# ----------------------------------------------------------------------


def test_multicollinearity_flag_when_vif_gt_10() -> None:
    """Build a near-collinear pair and confirm flag fires."""
    df = _synthetic_complete_case(n=200, seed=99)
    df["digital_efficacy_z"] = (
        df["motivation_z"] + np.random.default_rng(0).normal(0, 0.01, 200)
    )
    coefs, _ = compute_ols_regression(df)
    flagged = {c.axis_key for c in coefs if c.multicollinearity_flag}
    # Both motivation and digital_efficacy should hit the flag.
    assert "motivation" in flagged
    assert "digital_efficacy" in flagged


# ----------------------------------------------------------------------
# Fixed-meta fields
# ----------------------------------------------------------------------


def test_fit_method_literals() -> None:
    df = _synthetic_complete_case(n=80)
    _, fit = compute_ols_regression(df)
    assert fit.regression_method == "OLS"
    assert fit.multiple_comparison_method == "BH-FDR"


# ----------------------------------------------------------------------
# GAP-9 mitigation B — zero-variance predictor reject
# ----------------------------------------------------------------------


def test_zero_variance_predictor_rejected() -> None:
    """qa GAP-9 mitigation B: caller must reject sd_x=0 before statsmodels
    collapses the design matrix silently."""
    df = _synthetic_complete_case(n=80)
    df["motivation_z"] = 0.0  # constant ⇒ sd_x=0
    with pytest.raises(ValueError, match="zero-variance"):
        compute_ols_regression(df)


def test_near_zero_variance_passes_through() -> None:
    """sd_x=ε > 0 still passes — the guard is strict zero only."""
    df = _synthetic_complete_case(n=80)
    df["motivation_z"] = [1e-9 * i for i in range(80)]
    # No raise — VIF / coef may be unstable but no Fail-Fast.
    compute_ols_regression(df)


# ----------------------------------------------------------------------
# Insufficient sample
# ----------------------------------------------------------------------


def test_insufficient_complete_case_raises() -> None:
    """n_complete_case < 9 (must exceed degrees-of-freedom — 8 axes + intercept)
    cannot fit OLS — Fail-Fast."""
    df = _synthetic_complete_case(n=5)
    with pytest.raises(ValueError, match="complete-case"):
        compute_ols_regression(df)
