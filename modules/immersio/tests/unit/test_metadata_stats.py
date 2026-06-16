"""Unit tests for compute_metadata_aggregates (T026).

Spec 004 contracts/xlsx_sheets.md §3 — `2_메타데이터통계` 시트 + research §R-02
(Levene → ANOVA / Welch ANOVA / Welch t-test 자동 폴백).

8 metadata_kind 그룹별 통계 + 그룹간 차이 검정 결과를 MetadataAggregate list 로 산출.
"""

from __future__ import annotations

import immersio.ingest  # noqa: F401  # required-for: io ↔ ingest import order
import pandas as pd
import pytest
from immersio.analysis.metadata_stats import compute_metadata_aggregates  # noqa: E402
from paideia_shared.schemas import MetadataAggregate


def _build_section_fixture() -> tuple[pd.DataFrame, list[dict]]:
    """40 학생 × 4 분반 (10명씩). A 반 점수가 더 높음 → ANOVA p < 0.05.

    각 학생 1행 (응시자만), 점수 컬럼 'total_score', 분반 컬럼 'section'.
    """
    rng_seed = 42
    import numpy as np

    rng = np.random.default_rng(rng_seed)
    students = []
    for section_label, mean_offset in zip("ABCD", [10, 0, 0, 0]):
        for i in range(10):
            students.append(
                {
                    "student_id": f"{section_label}{i:02d}",
                    "section": section_label + "반",
                    "고교생물_이수": "이수" if i % 2 == 0 else "미이수",
                    "직업": "학생",
                    "total_score": float(120 + mean_offset + rng.normal(scale=5)),
                    # 챕터별 정답률은 metadata_aggregate 에서는 옵션 — 본 fixture 미사용
                }
            )
    student_df = pd.DataFrame(students)
    items = [
        {
            "item_no": 1,
            "chapter": "1장",
            "expected_difficulty": "보통",
            "difficulty_level": 3,
            "item_type": "지식축적",
            "source": "형성평가",
        },
    ]
    return student_df, items


def test_metadata_section_anova_or_welch_picked() -> None:
    """4 분반 평균 차이 → ANOVA 또는 Welch ANOVA 한 행이 채워짐."""
    student_df, items = _build_section_fixture()
    out = compute_metadata_aggregates(student_metrics_df=student_df, items=items)
    section_rows = [r for r in out if r.metadata_kind == "분반"]
    assert len(section_rows) >= 4  # A/B/C/D 각각 1행
    test_kinds = {r.test_kind for r in section_rows}
    # 적어도 하나의 행에 검정 결과 채움 (보통 첫 행 또는 별도 결과 행)
    assert "ANOVA" in test_kinds or "Welch ANOVA" in test_kinds


def test_metadata_two_category_uses_welch_t() -> None:
    """고교생물_이수 (yes/no 2 그룹) → Welch t-test."""
    student_df, items = _build_section_fixture()
    out = compute_metadata_aggregates(student_metrics_df=student_df, items=items)
    biology_rows = [r for r in out if r.metadata_kind == "고교생물_이수"]
    assert len(biology_rows) >= 2  # 이수 / 미이수
    test_kinds = {r.test_kind for r in biology_rows}
    assert "Welch t-test" in test_kinds


def test_metadata_missing_value_recorded_as_미정의() -> None:
    """``직업`` 결측 (NaN) 학생 → '(메타 미정의)' 카운트 행."""
    student_df, items = _build_section_fixture()
    student_df.loc[0:2, "직업"] = None  # 3명 결측
    out = compute_metadata_aggregates(student_metrics_df=student_df, items=items)
    job_rows = [r for r in out if r.metadata_kind == "직업"]
    undefined = [r for r in job_rows if r.metadata_value == "(메타 미정의)"]
    assert len(undefined) == 1
    assert undefined[0].n == 3


def test_metadata_groups_sum_to_responder_total() -> None:
    student_df, items = _build_section_fixture()
    out = compute_metadata_aggregates(student_metrics_df=student_df, items=items)
    section_rows = [r for r in out if r.metadata_kind == "분반"]
    n_total = sum(r.n for r in section_rows)
    assert n_total == len(student_df)  # 40명 합산


def test_metadata_aggregate_returns_pydantic() -> None:
    student_df, items = _build_section_fixture()
    out = compute_metadata_aggregates(student_metrics_df=student_df, items=items)
    assert all(isinstance(r, MetadataAggregate) for r in out)


def test_metadata_empty_input_raises() -> None:
    student_df = pd.DataFrame(columns=["student_id", "section", "total_score"])
    with pytest.raises(ValueError, match=r"empty"):
        compute_metadata_aggregates(
            student_metrics_df=student_df,
            items=[
                {
                    "item_no": 1,
                    "chapter": "1장",
                    "expected_difficulty": "보통",
                    "difficulty_level": 3,
                    "item_type": "지식축적",
                    "source": "형성평가",
                }
            ],
        )
