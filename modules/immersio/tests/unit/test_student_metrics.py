"""T046 — RED tests for `analysis/student_metrics.py::compute_student_metrics` (FR-013-018).

Public API:

    compute_student_metrics(
        exam_result_df: pd.DataFrame,
        student_master_df: pd.DataFrame,
        exam_items: list[ExamItem-like dict],
        needs_map_responses: list[dict] | None = None,
    ) -> list[StudentExamMetrics]

Behaviour under test:

* (a) 응시자 행만 백분위·z-score 채워짐 (Hazen + ddof=0)
* (b) 결시 학생 행 존재 + score 필드 None (StudentExamMetrics V1)
* (c) Hazen 백분위 동점자 → 절반 위·절반 아래
* (d) z_score = (score - mean) / pop_sd (ddof=0); pop_sd=0 이면 None
* (e) chapter_correct_rates dict 정확
* (f) 관심·비호감 챕터 정답률 (needs_map_responses 부재 시 None)
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from immersio.analysis.student_metrics import compute_student_metrics


def _exam_result_row(
    student_id: str,
    item_no: int,
    is_correct: bool,
    response: str | int | None = None,
    is_omit: bool = False,
) -> dict:
    return {
        "student_id": student_id,
        "item_no": item_no,
        "response": response,
        "is_correct": is_correct,
        "is_omit": is_omit,
    }


def _master_row(
    student_id: str,
    *,
    exam_taken: bool,
    section: str | None = "A",
    name_kr: str = "홍길동",
) -> dict:
    return {
        "student_id": student_id,
        "name_kr": name_kr,
        "section": section,
        "exam_taken": exam_taken,
        "exam_absent": (not exam_taken) and (section is not None),
        "on_roster": section is not None,
    }


def _item(item_no: int, *, chapter: str = "1장. 서론", source: str = "교과서",
          difficulty_level: int = 2, expected_difficulty: str = "보통",
          item_type: str = "지식축적") -> dict:
    return {
        "item_no": item_no,
        "chapter": chapter,
        "source": source,
        "difficulty_level": difficulty_level,
        "expected_difficulty": expected_difficulty,
        "item_type": item_type,
    }


def _build_synthetic_cohort() -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """7 takers + 3 absents × 4 items spanning two chapters."""
    items = [
        _item(1, chapter="1장. 서론", source="교과서"),
        _item(2, chapter="1장. 서론", source="교과서"),
        _item(3, chapter="2장. 세포와 조직", source="형성평가",
              difficulty_level=3, expected_difficulty="어려움"),
        _item(4, chapter="2장. 세포와 조직", source="형성평가",
              difficulty_level=3, expected_difficulty="어려움"),
    ]

    masters = [
        # 7 takers — diverse score distribution so percentile/z-score
        # checks have spread.
        _master_row("2026100001", exam_taken=True, section="A"),  # 4/4 = 100
        _master_row("2026100002", exam_taken=True, section="A"),  # 3/4 = 75
        _master_row("2026100003", exam_taken=True, section="A"),  # 3/4 = 75 (tie)
        _master_row("2026100004", exam_taken=True, section="B"),  # 2/4 = 50
        _master_row("2026100005", exam_taken=True, section="B"),  # 2/4 = 50 (tie)
        _master_row("2026100006", exam_taken=True, section="B"),  # 1/4 = 25
        _master_row("2026100007", exam_taken=True, section="B"),  # 0/4 = 0
        # 3 absents
        _master_row("2026100008", exam_taken=False, section="A"),
        _master_row("2026100009", exam_taken=False, section="B"),
        _master_row("2026100010", exam_taken=False, section="A"),
    ]

    correctness = {
        "2026100001": [True, True, True, True],
        "2026100002": [True, True, True, False],
        "2026100003": [True, True, False, True],
        "2026100004": [True, True, False, False],
        "2026100005": [True, False, True, False],
        "2026100006": [True, False, False, False],
        "2026100007": [False, False, False, False],
    }
    rows: list[dict] = []
    for sid, flags in correctness.items():
        for i, ok in enumerate(flags, start=1):
            rows.append(_exam_result_row(sid, i, ok))
    exam_df = pd.DataFrame(rows)
    master_df = pd.DataFrame(masters)
    return exam_df, master_df, items


def test_takers_have_score_and_percentile_z() -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
    )
    by_id = {m.student_id: m for m in metrics}
    s01 = by_id["2026100001"]
    assert s01.exam_taken is True
    assert s01.total_score == 4.0
    assert s01.score_percent == 100.0
    assert s01.cohort_percentile is not None
    assert s01.section_percentile is not None
    assert s01.z_score is not None


def test_absents_have_none_scores_and_pass_v1(student_metrics_helper=None) -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
    )
    by_id = {m.student_id: m for m in metrics}
    for absent_id in ("2026100008", "2026100009", "2026100010"):
        m = by_id[absent_id]
        assert m.exam_taken is False
        assert m.total_score is None
        assert m.score_percent is None
        assert m.section_percentile is None
        assert m.cohort_percentile is None
        assert m.z_score is None


def test_hazen_percentile_treats_ties_with_half_split() -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
    )
    by_id = {m.student_id: m for m in metrics}
    s02_pct = by_id["2026100002"].cohort_percentile
    s03_pct = by_id["2026100003"].cohort_percentile
    assert s02_pct is not None and s03_pct is not None
    # Hazen with half-split → tied scores receive identical percentile
    assert math.isclose(s02_pct, s03_pct, abs_tol=1e-9), (
        f"tied scores diverge: S02={s02_pct} S03={s03_pct}"
    )


def test_z_score_uses_population_sd_ddof_zero() -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
    )
    takers = [m for m in metrics if m.exam_taken]
    scores = [m.total_score for m in takers if m.total_score is not None]
    pop_mean = sum(scores) / len(scores)
    pop_sd = math.sqrt(sum((s - pop_mean) ** 2 for s in scores) / len(scores))
    by_id = {m.student_id: m for m in takers}
    s01_expected = (by_id["2026100001"].total_score - pop_mean) / pop_sd
    assert math.isclose(by_id["2026100001"].z_score, s01_expected, abs_tol=1e-9)


def test_chapter_correct_rates_dict_present_and_correct() -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
    )
    by_id = {m.student_id: m for m in metrics}
    # S01 got all 4 right → both chapters at 1.0
    assert by_id["2026100001"].chapter_correct_rates["1장. 서론"] == 1.0
    assert by_id["2026100001"].chapter_correct_rates["2장. 세포와 조직"] == 1.0
    # S04 got items 1+2 right (chapter 1) and missed 3+4 (chapter 2)
    assert by_id["2026100004"].chapter_correct_rates["1장. 서론"] == 1.0
    assert by_id["2026100004"].chapter_correct_rates["2장. 세포와 조직"] == 0.0


def test_source_and_difficulty_dicts_populated() -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
    )
    by_id = {m.student_id: m for m in metrics}
    s02 = by_id["2026100002"]
    # 교과서 (items 1+2) S02 → 2/2 = 1.0
    assert s02.source_correct_rates["교과서"] == 1.0
    # 형성평가 (items 3+4) S02 → 1/2 = 0.5
    assert s02.source_correct_rates["형성평가"] == 0.5
    # difficulty_level=2 → items 1+2; difficulty_level=3 → items 3+4
    assert s02.difficulty_correct_rates[2] == 1.0
    assert s02.difficulty_correct_rates[3] == 0.5
    # expected difficulty
    assert s02.expected_difficulty_correct_rates["보통"] == 1.0
    assert s02.expected_difficulty_correct_rates["어려움"] == 0.5


def test_interest_aversion_chapter_rates_none_when_no_needs_map() -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
        needs_map_responses=None,
    )
    for m in metrics:
        assert m.interest_chapters_correct_rate is None
        assert m.aversion_chapters_correct_rate is None


def test_interest_chapter_rate_computed_when_needs_map_present() -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    needs_map_resp = [
        {
            "student_id": "2026100001",
            "axis": "interest_topics",
            "axis_kind": "multiselect_onehot",
            "option_key": "세포와 조직",  # matches "2장. 세포와 조직"
            "value_bool": True,
        },
        {
            "student_id": "2026100002",
            "axis": "categorical_intent",
            "axis_kind": "multiselect_onehot",
            "option_key": "세포 조직학",  # matches "2장. 세포와 조직" only
            "value_bool": True,
        },
    ]
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
        needs_map_responses=needs_map_resp,
    )
    by_id = {m.student_id: m for m in metrics}
    # S01 got items 3+4 right (chapter 2) → interest rate = 2/2 = 1.0
    assert by_id["2026100001"].interest_chapters_correct_rate == 1.0
    # S02 got item 3 right + item 4 wrong → aversion rate = 0.5
    assert by_id["2026100002"].aversion_chapters_correct_rate == 0.5


def test_section_percentile_scoped_to_section() -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
    )
    by_id = {m.student_id: m for m in metrics}
    # S01 (highest in section A among 3 takers) — section percentile must
    # be ≥ cohort percentile-equivalent only if the section's distribution
    # is shifted relative to the cohort. Simple check: S01 (only top in A
    # section) gets the maximum Hazen percentile within section A.
    section_a_takers = [m for m in metrics if m.section == "A" and m.exam_taken]
    max_pct = max(m.section_percentile for m in section_a_takers)
    assert by_id["2026100001"].section_percentile == max_pct


def test_zero_sd_yields_none_z_score() -> None:
    # All 3 takers same score → sd=0 → z=None
    items = [_item(1, chapter="1장. 서론")]
    masters = [
        _master_row("2026100100", exam_taken=True, section="A"),
        _master_row("2026100200", exam_taken=True, section="A"),
        _master_row("2026100300", exam_taken=True, section="A"),
    ]
    rows = [
        _exam_result_row("2026100100", 1, True),
        _exam_result_row("2026100200", 1, True),
        _exam_result_row("2026100300", 1, True),
    ]
    metrics = compute_student_metrics(
        exam_result_df=pd.DataFrame(rows),
        student_master_df=pd.DataFrame(masters),
        exam_items=items,
    )
    for m in metrics:
        assert m.z_score is None


def test_takers_returned_sorted_by_student_id() -> None:
    exam_df, master_df, items = _build_synthetic_cohort()
    metrics = compute_student_metrics(
        exam_result_df=exam_df,
        student_master_df=master_df,
        exam_items=items,
    )
    sids = [m.student_id for m in metrics]
    assert sids == sorted(sids), "metrics must be sorted by student_id (deterministic)"


def test_rejects_empty_master_df() -> None:
    items = [_item(1)]
    with pytest.raises(ValueError):
        compute_student_metrics(
            exam_result_df=pd.DataFrame([]),
            student_master_df=pd.DataFrame([]),
            exam_items=items,
        )
