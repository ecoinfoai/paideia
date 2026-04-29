"""TDD tests for ``CorrelationCell`` (M2, T006). V1-V2."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paideia_shared.schemas.correlation_cell import CorrelationCell


def test_n_zero_with_all_none_passes() -> None:
    cell = CorrelationCell(
        axis_key="motivation",
        exam_metric_key="total_score",
        n=0,
        pearson_r=None,
        raw_p=None,
        fdr_q=None,
        significant_after_correction=False,
        unstable_inference_flag=True,
    )
    assert cell.n == 0


def test_v1_n_zero_with_pearson_r_raises() -> None:
    with pytest.raises(ValidationError, match="V1 n=0 nullness"):
        CorrelationCell(
            axis_key="motivation",
            exam_metric_key="total_score",
            n=0,
            pearson_r=0.5,
            raw_p=None,
            fdr_q=None,
            significant_after_correction=False,
            unstable_inference_flag=True,
        )


def test_v1_n_zero_with_significant_true_raises() -> None:
    with pytest.raises(ValidationError, match="V1 n=0 nullness"):
        CorrelationCell(
            axis_key="motivation",
            exam_metric_key="total_score",
            n=0,
            pearson_r=None,
            raw_p=None,
            fdr_q=None,
            significant_after_correction=True,
            unstable_inference_flag=True,
        )


def test_v2_q_above_one_raises() -> None:
    with pytest.raises(ValidationError, match="V2 q range"):
        CorrelationCell(
            axis_key="motivation",
            exam_metric_key="total_score",
            n=120,
            pearson_r=0.45,
            raw_p=0.001,
            fdr_q=1.5,
            significant_after_correction=False,
            unstable_inference_flag=False,
        )


def test_v2_q_negative_raises() -> None:
    with pytest.raises(ValidationError, match="V2 q range"):
        CorrelationCell(
            axis_key="motivation",
            exam_metric_key="total_score",
            n=120,
            pearson_r=0.45,
            raw_p=0.001,
            fdr_q=-0.1,
            significant_after_correction=False,
            unstable_inference_flag=False,
        )


def test_valid_significant_cell() -> None:
    cell = CorrelationCell(
        axis_key="motivation",
        exam_metric_key="chapter_신경계",
        n=160,
        pearson_r=0.45,
        raw_p=0.001,
        fdr_q=0.012,
        significant_after_correction=True,
        unstable_inference_flag=False,
    )
    assert cell.significant_after_correction is True


def test_invalid_axis_key_rejected() -> None:
    with pytest.raises(ValidationError):
        CorrelationCell(
            axis_key="not_an_axis",  # type: ignore[arg-type]
            exam_metric_key="total_score",
            n=120,
            pearson_r=0.0,
            raw_p=0.5,
            fdr_q=0.5,
            significant_after_correction=False,
            unstable_inference_flag=False,
        )


def test_unstable_inference_flag_n_lt_20() -> None:
    """n<20 셀의 unstable_inference_flag 는 caller 가 설정 — 모델은 boolean 값만 받음."""
    cell = CorrelationCell(
        axis_key="time_availability",
        exam_metric_key="total_score",
        n=18,
        pearson_r=0.31,
        raw_p=0.21,
        fdr_q=0.45,
        significant_after_correction=False,
        unstable_inference_flag=True,
    )
    assert cell.unstable_inference_flag is True
