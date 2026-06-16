"""compute_overall_summary — 전체요약 시트 13행 산출 (T034, FR-006).

Spec 004 contracts/xlsx_sheets.md §1 정합:
응시자수·결시자수·무응답응답수·만점·평균·SD·median·최저·최고·Q1·Q3·100환산_평균·100환산_SD.

결시 정책 (research §R-04): 통계는 응시자만으로 계산.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

OVERALL_SUMMARY_LABELS: tuple[str, ...] = (
    "응시자 수",
    "결시자 수",
    "무응답 응답 수",
    "만점",
    "평균",
    "표준편차",
    "중앙값",
    "최저",
    "최고",
    "Q1",
    "Q3",
    "100점환산_평균",
    "100점환산_표준편차",
)
"""Canonical row order for the 전체요약 sheet (FR-006)."""


def compute_overall_summary(
    exam_result_df: pd.DataFrame,
    student_master_df: pd.DataFrame,
) -> list[dict[str, object]]:
    """Compute the 13-row 전체요약 sheet payload.

    Args:
        exam_result_df: One row per responder. Required columns:
            ``student_id``, ``exam_total_score`` (float), ``exam_max_score``
            (float), ``n_omit_responses`` (int — per-student count of blank
            responses, used to aggregate the 무응답 응답 수 row).
        student_master_df: One row per enrolled student. Required columns:
            ``student_id``, ``exam_taken`` (bool).

    Returns:
        List of 13 ``{"지표": str, "값": float | int}`` dicts in the canonical
        order described by ``OVERALL_SUMMARY_LABELS``.

    Raises:
        ValueError: When all students are absent (no responders → mean / SD
            undefined). Fail-fast per Constitution V.
    """
    if "exam_taken" not in student_master_df.columns:
        raise ValueError(
            "compute_overall_summary: student_master_df must contain 'exam_taken' column"
        )

    n_responders = int(student_master_df["exam_taken"].sum())
    n_absent = int((~student_master_df["exam_taken"]).sum())
    if n_responders == 0:
        raise ValueError(
            "compute_overall_summary: no responders (all students absent); "
            "cannot compute mean/SD/quantiles"
        )

    if exam_result_df.empty:
        raise ValueError("compute_overall_summary: exam_result_df is empty but n_responders > 0")

    scores = exam_result_df["exam_total_score"].dropna().to_numpy(dtype=float)
    if scores.size == 0:
        raise ValueError("compute_overall_summary: exam_total_score column has no valid values")

    n_omit_responses = int(exam_result_df["n_omit_responses"].fillna(0).astype(int).sum())
    max_score = float(exam_result_df["exam_max_score"].iloc[0])

    mean = float(np.mean(scores))
    sd = float(np.std(scores, ddof=1)) if scores.size >= 2 else 0.0
    median = float(np.median(scores))
    minimum = float(np.min(scores))
    maximum = float(np.max(scores))
    q1 = float(np.percentile(scores, 25, method="linear"))
    q3 = float(np.percentile(scores, 75, method="linear"))

    if max_score > 0:
        mean_100 = mean / max_score * 100.0
        sd_100 = sd / max_score * 100.0
    else:
        raise ValueError(f"compute_overall_summary: max_score must be > 0, got {max_score}")

    values: dict[str, float | int] = {
        "응시자 수": n_responders,
        "결시자 수": n_absent,
        "무응답 응답 수": n_omit_responses,
        "만점": max_score,
        "평균": mean,
        "표준편차": sd,
        "중앙값": median,
        "최저": minimum,
        "최고": maximum,
        "Q1": q1,
        "Q3": q3,
        "100점환산_평균": mean_100,
        "100점환산_표준편차": sd_100,
    }
    return [{"지표": label, "값": values[label]} for label in OVERALL_SUMMARY_LABELS]
