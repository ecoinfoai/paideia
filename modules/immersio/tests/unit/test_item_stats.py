"""Unit tests for compute_item_statistics (T028).

Spec 004 contracts/xlsx_sheets.md §4-§6 + research §R-04 (결시 제외, 무응답 분모 포함).
``compute_item_statistics`` integrates discrimination + distractor_labels +
ItemStatistics schema in one call. 본 테스트는 응답 long-form 입력 + ExamItem
fixture → ItemStatistics list 의 정확성을 검증.
"""

from __future__ import annotations

import pandas as pd
import pytest

import immersio.ingest  # noqa: F401  # required-for: io ↔ ingest import order

from immersio.analysis.item_stats import compute_item_statistics  # noqa: E402
from paideia_shared.schemas import ItemStatistics


def _build_simple_fixture() -> tuple[pd.DataFrame, list[dict]]:
    """5 응시자 × 1 문항.

    response 분포: 정답 1, 오답 (보기 2) 2명, 오답 (보기 5) 1명, 무응답 1명.
    정답=1 → top_distractor 는 보기 2 (인접하지 않음? 1↔2 인접).
    correct_rate = 1/5 (무응답 포함 분모, 무응답=오답).
    omit_rate = 1/5.
    option_distribution: {1: 0.2, 2: 0.4, 5: 0.2} (무응답 제외 정답·오답만).
    top_distractor_no = 2, rate = 2/5 = 0.4, adjacent (1과 2 인접) = True.
    """
    item_meta = [
        {
            "item_no": 1,
            "chapter": "1장",
            "week": 1,
            "item_type": "지식축적",
            "difficulty_level": 3,
            "expected_difficulty": "보통",
            "source": "형성평가",
            "correct_answer": 1,
        }
    ]
    responses_long = pd.DataFrame(
        {
            "student_id": ["S1", "S2", "S3", "S4", "S5"],
            "item_no": [1, 1, 1, 1, 1],
            "response": ["1", "2", "2", "5", None],
        }
    )
    return responses_long, item_meta


def test_item_stats_basic_correctness() -> None:
    responses_long, item_meta = _build_simple_fixture()
    out = compute_item_statistics(
        responses_long=responses_long,
        items=item_meta,
        semester="2026-1",
        course_slug="anatomy",
    )
    assert len(out) == 1
    item = out[0]
    assert isinstance(item, ItemStatistics)
    assert item.item_no == 1
    assert item.n_responders == 5
    assert item.n_correct == 1
    assert item.n_omit == 1
    assert item.correct_rate == pytest.approx(0.2)
    assert item.omit_rate == pytest.approx(0.2)


def test_item_stats_top_distractor_adjacent() -> None:
    responses_long, item_meta = _build_simple_fixture()
    out = compute_item_statistics(
        responses_long=responses_long,
        items=item_meta,
        semester="2026-1",
        course_slug="anatomy",
    )
    item = out[0]
    assert item.top_distractor_no == 2  # 정답 1, top distractor 보기 2 (2명)
    assert item.top_distractor_rate == pytest.approx(0.4)  # 2/5
    assert item.is_top_distractor_adjacent is True  # 1과 2 인접


def test_item_stats_option_distribution_excludes_blank() -> None:
    responses_long, item_meta = _build_simple_fixture()
    out = compute_item_statistics(
        responses_long=responses_long,
        items=item_meta,
        semester="2026-1",
        course_slug="anatomy",
    )
    item = out[0]
    # 무응답 제외 distribution: 1=0.2, 2=0.4, 5=0.2 (sum=0.8, omit=0.2 외부)
    assert item.option_distribution[1] == pytest.approx(0.2)
    assert item.option_distribution[2] == pytest.approx(0.4)
    assert item.option_distribution[5] == pytest.approx(0.2)
    assert sum(item.option_distribution.values()) == pytest.approx(0.8)


def test_item_stats_non_adjacent_top_distractor() -> None:
    """정답=3, top_distractor=5 → 인접 아님 (3↔4 만 인접)."""
    item_meta = [
        {
            "item_no": 1,
            "chapter": "1장",
            "week": 1,
            "item_type": "이해",
            "difficulty_level": 2,
            "expected_difficulty": "보통",
            "source": "형성평가",
            "correct_answer": 3,
        }
    ]
    responses_long = pd.DataFrame(
        {
            "student_id": [f"S{i}" for i in range(10)],
            "item_no": [1] * 10,
            "response": ["3", "3", "5", "5", "5", "5", "5", "1", "2", "4"],
        }
    )
    out = compute_item_statistics(
        responses_long=responses_long,
        items=item_meta,
        semester="2026-1",
        course_slug="anatomy",
    )
    item = out[0]
    assert item.top_distractor_no == 5
    assert item.is_top_distractor_adjacent is False  # 3과 5 인접 아님


def test_item_stats_no_distractor_chosen_above_zero_returns_none() -> None:
    """모든 학생이 정답 → top_distractor 없음 (None)."""
    item_meta = [
        {
            "item_no": 1,
            "chapter": "1장",
            "week": 1,
            "item_type": "지식축적",
            "difficulty_level": 1,
            "expected_difficulty": "쉬움",
            "source": "형성평가",
            "correct_answer": 2,
        }
    ]
    responses_long = pd.DataFrame(
        {
            "student_id": ["S1", "S2", "S3"],
            "item_no": [1, 1, 1],
            "response": ["2", "2", "2"],
        }
    )
    out = compute_item_statistics(
        responses_long=responses_long,
        items=item_meta,
        semester="2026-1",
        course_slug="anatomy",
    )
    item = out[0]
    assert item.top_distractor_no is None
    assert item.top_distractor_rate is None
    assert item.is_top_distractor_adjacent is False
    assert item.correct_rate == pytest.approx(1.0)


def test_item_stats_distractor_label_populated() -> None:
    """ItemStatistics.distractor_label 은 룰셋 평가 결과로 채워져야 한다."""
    responses_long, item_meta = _build_simple_fixture()
    out = compute_item_statistics(
        responses_long=responses_long,
        items=item_meta,
        semester="2026-1",
        course_slug="anatomy",
    )
    item = out[0]
    # discrimination/point_biserial 산출은 별도 dict 입력 필요 — 본 테스트는
    # 그 인자가 None 이면 'discrimination=0.0' 가정 + 'point_biserial=None'.
    # correct_rate=0.2 < 0.30 인데 D=0.0 (D > 0.30 미충족) → rule 3 미적용,
    # rule 4 (omit > 0.10): omit=0.2 > 0.10 → '시간 부족 또는 포기형'
    assert item.distractor_label == "시간 부족 또는 포기형"


def test_item_stats_with_total_scores_includes_discrimination() -> None:
    """total_scores 가 주어지면 D / point_biserial 가 채워진다."""
    item_meta = [
        {
            "item_no": 1,
            "chapter": "1장",
            "week": 1,
            "item_type": "지식축적",
            "difficulty_level": 3,
            "expected_difficulty": "보통",
            "source": "형성평가",
            "correct_answer": 1,
        }
    ]
    responses_long = pd.DataFrame(
        {
            "student_id": [f"S{i}" for i in range(10)],
            "item_no": [1] * 10,
            "response": ["1", "1", "1", "2", "2", "2", "2", "2", "2", "2"],
        }
    )
    total_scores = {f"S{i}": float(20 - i) for i in range(10)}
    out = compute_item_statistics(
        responses_long=responses_long,
        items=item_meta,
        semester="2026-1",
        course_slug="anatomy",
        total_scores=total_scores,
    )
    item = out[0]
    # 상위 학생 (높은 score) 일수록 정답이 많음 → D > 0
    assert item.discrimination_index > 0
