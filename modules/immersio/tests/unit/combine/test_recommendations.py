"""TDD tests for ``combine.recommendations`` (T025, US1).

Verifies the rule-based prescriptive section generation (FR-017, FR-018,
FR-019, FR-019a — NO LLM, deterministic templates only).

Three top-3 branches:
- 3+ axes 유의 ⇒ 정확히 3 axes
- 1-2 axes 유의 ⇒ 가용한 모든 유의 axis
- 0 axes 유의 ⇒ all-non-significant fallback 메시지

Plus warnings: n<30 small-sample + VIF>10 multicollinearity.

Determinism: tie-breaker on axis_key alphabetic (research §R9). Two
equal-|β| axes must always emerge in alphabetic order — verified by
identity 재실행.
"""

from __future__ import annotations

import pytest

from immersio.combine.recommendations import build_recommendations
from paideia_shared.schemas import RegressionCoefficient, RegressionFitSummary
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS


def _coef(
    axis: str,
    *,
    coef: float = 0.0,
    raw_p: float = 0.5,
    fdr_q: float = 0.5,
    vif: float = 1.0,
) -> RegressionCoefficient:
    return RegressionCoefficient(
        axis_key=axis,
        coef=coef,
        std_err=0.5,
        t_stat=coef / 0.5,
        raw_p=raw_p,
        fdr_q=fdr_q,
        ci_low_95=coef - 1.0,
        ci_high_95=coef + 1.0,
        beta_standardized=coef / 10.0,
        vif=vif,
        multicollinearity_flag=vif > 10.0,
    )


def _fit(*, n: int = 50, vif_max: float = 1.0) -> RegressionFitSummary:
    return RegressionFitSummary(
        n_complete_case=n,
        n_dropped=0,
        r2=0.4,
        r2_adj=0.35,
        f_stat=10.0,
        f_pvalue=0.01,
        regression_method="OLS",
        multiple_comparison_method="BH-FDR",
        small_sample_warning=n < 30,
    )


# ----------------------------------------------------------------------
# Top-3 selection
# ----------------------------------------------------------------------


def test_returns_dict_with_section_keys() -> None:
    coefs = [_coef(a, coef=0.5, fdr_q=0.5) for a in STANDARD_AXIS_KEYS]
    out = build_recommendations(coefs, _fit())
    assert isinstance(out, dict)
    assert "top3_axes" in out
    assert "prescriptive_text" in out


def test_top3_returns_three_when_more_than_three_significant() -> None:
    coefs = [
        _coef("motivation", coef=5.0, fdr_q=0.001),
        _coef("study_strategy", coef=4.0, fdr_q=0.002),
        _coef("digital_efficacy", coef=3.0, fdr_q=0.01),
        _coef("time_availability", coef=2.0, fdr_q=0.04),
        _coef("material_preference", coef=1.0, fdr_q=0.05),  # excluded (q=0.05)
        _coef("study_environment", coef=0.5, fdr_q=0.6),
        _coef("social_learning", coef=0.3, fdr_q=0.7),
        _coef("feedback_seeking", coef=0.2, fdr_q=0.8),
    ]
    out = build_recommendations(coefs, _fit())
    assert out["top3_axes"] == [
        "motivation",
        "study_strategy",
        "digital_efficacy",
    ]


def test_top3_returns_two_when_only_two_significant() -> None:
    coefs = [_coef(a, coef=0.0, fdr_q=0.5) for a in STANDARD_AXIS_KEYS]
    coefs[0] = _coef(STANDARD_AXIS_KEYS[0], coef=5.0, fdr_q=0.01)
    coefs[1] = _coef(STANDARD_AXIS_KEYS[1], coef=3.0, fdr_q=0.02)
    out = build_recommendations(coefs, _fit())
    assert len(out["top3_axes"]) == 2


def test_top3_empty_when_no_significant() -> None:
    coefs = [_coef(a, coef=1.0, fdr_q=0.5) for a in STANDARD_AXIS_KEYS]
    out = build_recommendations(coefs, _fit())
    assert out["top3_axes"] == []
    assert "유의" in out["prescriptive_text"]


def test_q_strictly_less_than_005() -> None:
    """FR-019a: q<0.05 (strict). q=0.05 excluded."""
    coefs = [_coef(a, coef=1.0, fdr_q=0.5) for a in STANDARD_AXIS_KEYS]
    coefs[0] = _coef(STANDARD_AXIS_KEYS[0], coef=5.0, fdr_q=0.05)  # excluded
    coefs[1] = _coef(STANDARD_AXIS_KEYS[1], coef=2.0, fdr_q=0.04)  # included
    out = build_recommendations(coefs, _fit())
    assert STANDARD_AXIS_KEYS[0] not in out["top3_axes"]
    assert STANDARD_AXIS_KEYS[1] in out["top3_axes"]


# ----------------------------------------------------------------------
# Tie-breaker — research §R9 alphabetic on equal |β|
# ----------------------------------------------------------------------


def test_tie_breaker_alphabetic_axis_key() -> None:
    """Two axes with identical |β| ⇒ alphabetic axis_key first."""
    coefs = [_coef(a, coef=0.0, fdr_q=0.5) for a in STANDARD_AXIS_KEYS]
    # 'digital_efficacy' < 'motivation' alphabetically.
    coefs[0] = _coef("motivation", coef=2.0, fdr_q=0.01)
    coefs[1] = _coef("digital_efficacy", coef=2.0, fdr_q=0.01)
    out = build_recommendations(coefs, _fit())
    assert out["top3_axes"][0] == "digital_efficacy"
    assert out["top3_axes"][1] == "motivation"


def test_deterministic_repeat_call() -> None:
    coefs = [
        _coef("motivation", coef=5.0, fdr_q=0.001),
        _coef("study_strategy", coef=5.0, fdr_q=0.001),  # tie with motivation
        _coef("digital_efficacy", coef=3.0, fdr_q=0.01),
        _coef("time_availability", coef=0.0, fdr_q=0.5),
        _coef("material_preference", coef=0.0, fdr_q=0.5),
        _coef("study_environment", coef=0.0, fdr_q=0.5),
        _coef("social_learning", coef=0.0, fdr_q=0.5),
        _coef("feedback_seeking", coef=0.0, fdr_q=0.5),
    ]
    out1 = build_recommendations(coefs, _fit())
    out2 = build_recommendations(coefs, _fit())
    assert out1["top3_axes"] == out2["top3_axes"]


# ----------------------------------------------------------------------
# Negative β handled by absolute value
# ----------------------------------------------------------------------


def test_top3_uses_absolute_beta() -> None:
    """Strong negative |β| should rank above weak positive."""
    coefs = [_coef(a, coef=0.0, fdr_q=0.5) for a in STANDARD_AXIS_KEYS]
    coefs[0] = _coef("motivation", coef=-5.0, fdr_q=0.001)
    coefs[1] = _coef("study_strategy", coef=1.0, fdr_q=0.01)
    out = build_recommendations(coefs, _fit())
    assert out["top3_axes"][0] == "motivation"


# ----------------------------------------------------------------------
# Warnings — small sample + multicollinearity
# ----------------------------------------------------------------------


def test_small_sample_warning_appended_when_n_lt_30() -> None:
    coefs = [_coef(a, coef=1.0, fdr_q=0.01) for a in STANDARD_AXIS_KEYS]
    out = build_recommendations(coefs, _fit(n=25))
    assert "n<30" in out["prescriptive_text"] or "표본" in out["prescriptive_text"]


def test_no_small_sample_warning_when_n_ge_30() -> None:
    coefs = [_coef(a, coef=1.0, fdr_q=0.01) for a in STANDARD_AXIS_KEYS]
    out = build_recommendations(coefs, _fit(n=100))
    assert "n<30" not in out["prescriptive_text"]


def test_multicollinearity_warning_when_any_vif_gt_10() -> None:
    coefs = [_coef(a, coef=1.0, fdr_q=0.01, vif=1.0) for a in STANDARD_AXIS_KEYS]
    coefs[0] = _coef(STANDARD_AXIS_KEYS[0], coef=1.0, fdr_q=0.01, vif=15.0)
    out = build_recommendations(coefs, _fit(n=50))
    text = out["prescriptive_text"]
    assert "다중공선성" in text or "VIF" in text


def test_no_multicollinearity_warning_when_all_vif_le_10() -> None:
    coefs = [_coef(a, coef=1.0, fdr_q=0.01, vif=2.0) for a in STANDARD_AXIS_KEYS]
    out = build_recommendations(coefs, _fit(n=50))
    assert "다중공선성" not in out["prescriptive_text"]


# ----------------------------------------------------------------------
# Empty input (Fail-Fast)
# ----------------------------------------------------------------------


def test_empty_coefs_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        build_recommendations([], _fit())
