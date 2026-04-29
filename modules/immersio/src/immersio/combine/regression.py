"""OLS multiple regression: total_score ~ 8 z-axes + VIF (T027, US1).

FR-006 (OLS), FR-013 (multicollinearity via VIF > 10), research §R2
(statsmodels, NOT scikit-learn — needs p-values + CI), §R7 (effect sizes
from same module — see ``combine.effect_sizes``).

Public API:
- :func:`compute_ols_regression(df)` — returns ``(list[RegressionCoefficient],
  RegressionFitSummary)``.

GAP-9 mitigation B (qa-engineer 2026-04-30): caller-layer Fail-Fast on
zero-variance predictors. Statsmodels would silently collapse the design
matrix when an axis is constant; we reject before that happens so the
manifest never records a regression result derived from an invalid
design.
"""

from __future__ import annotations

import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

from paideia_shared.schemas import RegressionCoefficient, RegressionFitSummary
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS

from .fdr import bh_fdr_adjust

_VIF_THRESHOLD = 10.0  # FR-013
_MIN_COMPLETE_CASE = 9  # 8 axes + intercept; OLS cannot fit otherwise
_SMALL_SAMPLE_THRESHOLD = 30


def compute_ols_regression(
    df: pd.DataFrame,
) -> tuple[list[RegressionCoefficient], RegressionFitSummary]:
    """Fit ``total_score ~ 1 + 8 z-axes`` via OLS, then BH-FDR adjust the 8 p-values.

    Args:
        df: Joiner output. Must carry ``total_score`` plus the 8
            ``{axis}_z`` columns.

    Returns:
        Tuple of (per-axis coefficients, fit summary). Coefficient list
        is in ``STANDARD_AXIS_KEYS`` order.

    Raises:
        ValueError: If any predictor is zero-variance on the
            complete-case sub-frame (GAP-9 mitigation B), or if the
            complete-case sample is too small to fit (n < 9).
    """
    z_cols = [f"{axis}_z" for axis in STANDARD_AXIS_KEYS]
    cols_needed = ["total_score", *z_cols]

    base = df[cols_needed].copy()
    if "exam_taken" in df.columns:
        base = base[df["exam_taken"].astype(bool).to_numpy()]

    n_eligible = len(base)
    complete = base.dropna()
    n_complete = len(complete)
    n_dropped = n_eligible - n_complete

    if n_complete < _MIN_COMPLETE_CASE:
        raise ValueError(
            f"compute_ols_regression: complete-case n={n_complete} below "
            f"minimum {_MIN_COMPLETE_CASE} (8 predictors + intercept)"
        )

    # GAP-9 mitigation B — zero-variance predictor reject.
    for axis in STANDARD_AXIS_KEYS:
        sd = float(complete[f"{axis}_z"].std(ddof=1))
        if sd == 0.0:
            raise ValueError(
                f"compute_ols_regression: zero-variance predictor "
                f"{axis!r} on complete-case sub-frame — pipeline anomaly "
                f"(qa GAP-9 mitigation B)"
            )

    X = complete[z_cols]
    y = complete["total_score"]
    X_const = sm.add_constant(X)
    model = sm.OLS(y, X_const).fit()

    raw_ps = [float(model.pvalues[f"{axis}_z"]) for axis in STANDARD_AXIS_KEYS]
    qs = bh_fdr_adjust(raw_ps)

    # Pre-compute VIFs for all 8 predictors.
    X_arr = X_const.to_numpy()
    vifs = [
        float(variance_inflation_factor(X_arr, i + 1))
        for i in range(len(STANDARD_AXIS_KEYS))
    ]

    # Standardised β: since predictors are already z-scored (sd=1) and the
    # outcome is total_score, β* = β · sd_x / sd_y reduces to β / sd_y.
    sd_y = float(y.std(ddof=1))

    coefs: list[RegressionCoefficient] = []
    ci = model.conf_int()
    for i, axis in enumerate(STANDARD_AXIS_KEYS):
        coef = float(model.params[f"{axis}_z"])
        se = float(model.bse[f"{axis}_z"])
        t = float(model.tvalues[f"{axis}_z"])
        ci_low = float(ci.loc[f"{axis}_z", 0])
        ci_high = float(ci.loc[f"{axis}_z", 1])
        coefs.append(
            RegressionCoefficient(
                axis_key=axis,
                coef=coef,
                std_err=se,
                t_stat=t,
                raw_p=raw_ps[i],
                fdr_q=qs[i],
                ci_low_95=ci_low,
                ci_high_95=ci_high,
                beta_standardized=(coef / sd_y) if sd_y > 0 else 0.0,
                vif=vifs[i],
                multicollinearity_flag=vifs[i] > _VIF_THRESHOLD,
            )
        )

    fit = RegressionFitSummary(
        n_complete_case=n_complete,
        n_dropped=n_dropped,
        # Clamp R² into [0, 1] (V2). statsmodels OLS with intercept
        # cannot produce negative R² in well-posed cases; the clamp is
        # defensive and surfaces the M4 r2 ge=0 invariant per
        # pair-programmer watch list §8.1.
        r2=max(0.0, min(1.0, float(model.rsquared))),
        r2_adj=min(1.0, float(model.rsquared_adj)),
        f_stat=float(model.fvalue),
        f_pvalue=float(model.f_pvalue),
        regression_method="OLS",
        multiple_comparison_method="BH-FDR",
        small_sample_warning=n_complete < _SMALL_SAMPLE_THRESHOLD,
    )
    return coefs, fit


__all__ = ["compute_ols_regression"]
