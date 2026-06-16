"""TDD tests for ``RegressionCoefficient`` (M3) + ``RegressionFitSummary`` (M4) (T007)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas.regression_summary import (
    RegressionCoefficient,
    RegressionFitSummary,
)
from pydantic import ValidationError

# RegressionCoefficient


def test_regression_coef_valid() -> None:
    coef = RegressionCoefficient(
        axis_key="motivation",
        coef=2.4,
        std_err=0.5,
        t_stat=4.8,
        raw_p=0.001,
        fdr_q=0.008,
        ci_low_95=1.4,
        ci_high_95=3.4,
        beta_standardized=0.32,
        vif=1.4,
        multicollinearity_flag=False,
    )
    assert coef.coef == 2.4


def test_v1_ci_low_above_coef_raises() -> None:
    with pytest.raises(ValidationError, match="V1 CI bounds"):
        RegressionCoefficient(
            axis_key="motivation",
            coef=2.0,
            std_err=0.5,
            t_stat=4.0,
            raw_p=0.001,
            fdr_q=0.008,
            ci_low_95=2.5,
            ci_high_95=3.5,
            beta_standardized=0.3,
            vif=1.4,
            multicollinearity_flag=False,
        )


def test_v1_coef_above_ci_high_raises() -> None:
    with pytest.raises(ValidationError, match="V1 CI bounds"):
        RegressionCoefficient(
            axis_key="motivation",
            coef=4.0,
            std_err=0.5,
            t_stat=8.0,
            raw_p=0.001,
            fdr_q=0.008,
            ci_low_95=1.0,
            ci_high_95=3.0,
            beta_standardized=0.3,
            vif=1.4,
            multicollinearity_flag=False,
        )


def test_negative_vif_raises() -> None:
    with pytest.raises(ValidationError):
        RegressionCoefficient(
            axis_key="motivation",
            coef=2.0,
            std_err=0.5,
            t_stat=4.0,
            raw_p=0.001,
            fdr_q=0.008,
            ci_low_95=1.0,
            ci_high_95=3.0,
            beta_standardized=0.3,
            vif=-1.0,
            multicollinearity_flag=False,
        )


def test_high_vif_with_multicollinearity_flag() -> None:
    """VIF > 10 case — multicollinearity_flag is caller's responsibility."""
    coef = RegressionCoefficient(
        axis_key="study_strategy",
        coef=1.5,
        std_err=0.8,
        t_stat=1.9,
        raw_p=0.06,
        fdr_q=0.12,
        ci_low_95=-0.1,
        ci_high_95=3.1,
        beta_standardized=0.20,
        vif=12.5,
        multicollinearity_flag=True,
    )
    assert coef.multicollinearity_flag is True


# RegressionFitSummary


def test_fit_summary_valid_above_30() -> None:
    summary = RegressionFitSummary(
        n_complete_case=142,
        n_dropped=23,
        r2=0.348,
        r2_adj=0.310,
        f_stat=8.94,
        f_pvalue=0.0001,
        regression_method="OLS",
        multiple_comparison_method="BH-FDR",
        small_sample_warning=False,
    )
    assert summary.r2 == pytest.approx(0.348)


def test_fit_summary_small_sample_below_30() -> None:
    summary = RegressionFitSummary(
        n_complete_case=22,
        n_dropped=5,
        r2=0.20,
        r2_adj=0.10,
        f_stat=2.0,
        f_pvalue=0.06,
        regression_method="OLS",
        multiple_comparison_method="BH-FDR",
        small_sample_warning=True,
    )
    assert summary.small_sample_warning is True


def test_v1_small_sample_warning_mismatch_low_n() -> None:
    """n=20 (<30) but warning=False → ValueError."""
    with pytest.raises(ValidationError, match="V1 small_sample_warning"):
        RegressionFitSummary(
            n_complete_case=20,
            n_dropped=0,
            r2=0.1,
            r2_adj=0.05,
            f_stat=1.0,
            f_pvalue=0.3,
            regression_method="OLS",
            multiple_comparison_method="BH-FDR",
            small_sample_warning=False,
        )


def test_v1_small_sample_warning_mismatch_high_n() -> None:
    """n=100 (≥30) but warning=True → ValueError."""
    with pytest.raises(ValidationError, match="V1 small_sample_warning"):
        RegressionFitSummary(
            n_complete_case=100,
            n_dropped=0,
            r2=0.3,
            r2_adj=0.28,
            f_stat=10.0,
            f_pvalue=0.0001,
            regression_method="OLS",
            multiple_comparison_method="BH-FDR",
            small_sample_warning=True,
        )


def test_invalid_method_literal() -> None:
    with pytest.raises(ValidationError):
        RegressionFitSummary(
            n_complete_case=100,
            n_dropped=0,
            r2=0.3,
            r2_adj=0.28,
            f_stat=10.0,
            f_pvalue=0.0001,
            regression_method="LASSO",  # type: ignore[arg-type]
            multiple_comparison_method="BH-FDR",
            small_sample_warning=False,
        )


def test_r2_above_one_rejected() -> None:
    with pytest.raises(ValidationError):
        RegressionFitSummary(
            n_complete_case=100,
            n_dropped=0,
            r2=1.5,
            r2_adj=0.28,
            f_stat=10.0,
            f_pvalue=0.0001,
            regression_method="OLS",
            multiple_comparison_method="BH-FDR",
            small_sample_warning=False,
        )
