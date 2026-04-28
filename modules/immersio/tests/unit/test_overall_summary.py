"""Unit tests for compute_overall_summary (T024).

Spec 004 contracts/xlsx_sheets.md §1 — 전체요약 시트 13행:
응시자수·결시자수·무응답응답수·만점·평균·SD·median·최저·최고·Q1·Q3·100환산_평균·100환산_SD.

결시 제외 정책 (research §R-04): 평균/SD/median/Q1/Q3/min/max 계산 시 결시 행 제외.
무응답은 응시자에 포함하되 오답으로 처리 — overall summary 에는 응답 카운트 (`무응답 응답 수`) 만 노출.
"""

from __future__ import annotations

import pandas as pd
import pytest

# Pre-populate ``immersio.ingest`` to break the io ↔ ingest circular import
# during standalone test collection (see test_attendance_roster_only.py).
import immersio.ingest  # noqa: F401  # required-for: io ↔ ingest import order

from immersio.analysis.overall_summary import (  # noqa: E402
    OVERALL_SUMMARY_LABELS,
    compute_overall_summary,
)


def _build_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    """10 students, 3 absent, 1 omit-only — used across multiple assertions.

    Scores (응시 7명, max=20):
        20, 18, 15, 14, 13, 11, 9 (mean=14.286, median=14, sd≈3.730).
    Omit responses: 1 across all responders (누적).
    """
    student_master = pd.DataFrame(
        {
            "student_id": [f"202600000{i+1}" for i in range(10)],
            "exam_taken": [True] * 7 + [False] * 3,
        }
    )
    exam_result = pd.DataFrame(
        {
            "student_id": [f"202600000{i+1}" for i in range(7)],
            "exam_total_score": [20.0, 18.0, 15.0, 14.0, 13.0, 11.0, 9.0],
            "exam_max_score": [20.0] * 7,
            "n_omit_responses": [0, 0, 0, 1, 0, 0, 0],
        }
    )
    return exam_result, student_master


def test_overall_summary_returns_13_rows_in_order() -> None:
    exam_result, student_master = _build_fixture()
    out = compute_overall_summary(exam_result, student_master)
    assert isinstance(out, list)
    assert [row["지표"] for row in out] == list(OVERALL_SUMMARY_LABELS)
    assert len(out) == 13


def test_overall_summary_responder_count_excludes_absent() -> None:
    exam_result, student_master = _build_fixture()
    rows = {row["지표"]: row["값"] for row in compute_overall_summary(exam_result, student_master)}
    assert rows["응시자 수"] == 7
    assert rows["결시자 수"] == 3
    assert rows["무응답 응답 수"] == 1


def test_overall_summary_max_score_uses_responders_value() -> None:
    exam_result, student_master = _build_fixture()
    rows = {row["지표"]: row["값"] for row in compute_overall_summary(exam_result, student_master)}
    assert rows["만점"] == 20.0


def test_overall_summary_descriptive_stats_match_responders_only() -> None:
    exam_result, student_master = _build_fixture()
    rows = {row["지표"]: row["값"] for row in compute_overall_summary(exam_result, student_master)}
    # Scores [20, 18, 15, 14, 13, 11, 9] → mean=14.286, median=14, ddof=1 sd≈3.817
    assert rows["평균"] == pytest.approx(14.285714, abs=1e-4)
    assert rows["중앙값"] == pytest.approx(14.0)
    assert rows["최저"] == 9.0
    assert rows["최고"] == 20.0
    assert rows["표준편차"] == pytest.approx(3.81725, abs=1e-3)


def test_overall_summary_quantiles_use_linear_method() -> None:
    """numpy.percentile linear interpolation (default)."""
    exam_result, student_master = _build_fixture()
    rows = {row["지표"]: row["값"] for row in compute_overall_summary(exam_result, student_master)}
    # numpy.percentile(linear) for [9, 11, 13, 14, 15, 18, 20]:
    # Q1 = 12.0 (between idx 1.5 → linear), Q3 = 16.5 (between idx 4.5 → linear).
    assert rows["Q1"] == pytest.approx(12.0)
    assert rows["Q3"] == pytest.approx(16.5)


def test_overall_summary_100point_normalization() -> None:
    exam_result, student_master = _build_fixture()
    rows = {row["지표"]: row["값"] for row in compute_overall_summary(exam_result, student_master)}
    expected_mean_100 = 14.285714 / 20.0 * 100.0
    expected_sd_100 = 3.81725 / 20.0 * 100.0
    assert rows["100점환산_평균"] == pytest.approx(expected_mean_100, abs=1e-2)
    assert rows["100점환산_표준편차"] == pytest.approx(expected_sd_100, abs=1e-2)


def test_overall_summary_all_absent_raises() -> None:
    """Fail-fast: 모든 학생이 결시면 ValueError (응시자 0명)."""
    student_master = pd.DataFrame(
        {"student_id": ["2026000001", "2026000002"], "exam_taken": [False, False]}
    )
    exam_result = pd.DataFrame(
        {
            "student_id": [],
            "exam_total_score": [],
            "exam_max_score": [],
            "n_omit_responses": [],
        }
    )
    with pytest.raises(ValueError, match=r"no responders"):
        compute_overall_summary(exam_result, student_master)
