"""Unit tests for compute_discrimination (T027).

Spec 004 research §R-03 — 27% top/bottom + 동점자 포함 + point-biserial:
- n_27 = round(n * 0.27, half-to-even)
- 총점 boundary 와 동점인 학생은 모두 포함 → 분모 가변
- D = top_correct_rate - bottom_correct_rate
- point_biserial 은 stat_tests.point_biserial 호출
"""

from __future__ import annotations

import immersio.ingest  # noqa: F401  # required-for: io ↔ ingest import order
import numpy as np
import pytest
from immersio.analysis.discrimination import compute_discrimination  # noqa: E402


def test_discrimination_basic_two_items() -> None:
    """4 학생 × 2 문항. n_27 = round(4 * 0.27) = round(1.08) = 1.

    학생: A(score=20, item1 correct, item2 wrong),
          B(score=15, item1 correct, item2 correct),
          C(score=12, item1 wrong, item2 correct),
          D(score=8,  item1 wrong, item2 wrong).
    상위27% (1명): A. 하위27% (1명): D.
    item1 D = 1.0 (A correct) - 0.0 (D wrong) = 1.0
    item2 D = 0.0 - 0.0 = 0.0
    """
    item_responses = {
        1: {"A": 1, "B": 1, "C": 0, "D": 0},
        2: {"A": 0, "B": 1, "C": 1, "D": 0},
    }
    total_scores = {"A": 20, "B": 15, "C": 12, "D": 8}
    out = compute_discrimination(item_responses, total_scores, top_pct=0.27)
    assert out[1].discrimination_index == pytest.approx(1.0)
    assert out[2].discrimination_index == pytest.approx(0.0)


def test_discrimination_tie_inflates_denominator() -> None:
    """n=10, top_pct=0.27 → n_27 = round(2.7) = 3 (half-to-even).

    Scores: 20, 18, 16, 14, 12, 10, 8, 8, 8, 5.
    상위 3 = 20/18/16. 하위 3 = 5/8/8. 그러나 8 동점이 3명이라 boundary
    학생 모두 포함 → 하위 분모는 4 (5, 8, 8, 8).
    """
    student_ids = list("ABCDEFGHIJ")
    scores_list = [20, 18, 16, 14, 12, 10, 8, 8, 8, 5]
    total_scores = dict(zip(student_ids, scores_list))
    # item1: 상위 3명 모두 정답, 하위 4명 모두 오답.
    item_responses = {
        1: dict(zip(student_ids, [1, 1, 1, 0, 0, 0, 0, 0, 0, 0])),
    }
    out = compute_discrimination(item_responses, total_scores, top_pct=0.27)
    # 상위 1.0, 하위 0.0 → D=1.0
    assert out[1].discrimination_index == pytest.approx(1.0)
    # bottom_n 은 4 (8 동점 3명 + 5 1명).
    assert out[1].bottom_n == 4
    assert out[1].top_n == 3


def test_discrimination_n_27_round_half_to_even() -> None:
    """n=8: round(8 * 0.27) = round(2.16) = 2."""
    student_ids = list("ABCDEFGH")
    scores_list = [20, 18, 16, 14, 12, 10, 8, 5]
    total_scores = dict(zip(student_ids, scores_list))
    item_responses = {
        1: dict(zip(student_ids, [1, 1, 0, 0, 0, 0, 0, 0])),
    }
    out = compute_discrimination(item_responses, total_scores, top_pct=0.27)
    assert out[1].top_n == 2
    assert out[1].bottom_n == 2


def test_discrimination_point_biserial_present() -> None:
    """point_biserial 은 None 또는 -1 ≤ r ≤ 1 사이 float."""
    rng = np.random.default_rng(31)
    student_ids = [f"S{i:03d}" for i in range(100)]
    scores_list = rng.normal(loc=15, scale=4, size=100)
    total_scores = dict(zip(student_ids, scores_list.tolist()))
    item_responses = {
        1: {sid: int(rng.random() < 0.6) for sid in student_ids},
    }
    out = compute_discrimination(item_responses, total_scores, top_pct=0.27)
    pb = out[1].point_biserial
    assert pb is None or -1.0 <= pb <= 1.0


def test_discrimination_constant_correctness_returns_zero_d() -> None:
    """모든 학생이 정답이면 D=0, point_biserial=None (constant binary)."""
    total_scores = {f"S{i}": float(i) for i in range(10)}
    item_responses = {1: dict.fromkeys(total_scores, 1)}
    out = compute_discrimination(item_responses, total_scores, top_pct=0.27)
    assert out[1].discrimination_index == pytest.approx(0.0)
    assert out[1].point_biserial is None


def test_discrimination_rejects_invalid_top_pct() -> None:
    with pytest.raises(ValueError, match=r"top_pct"):
        compute_discrimination({1: {"A": 1}}, {"A": 10}, top_pct=0.0)
    with pytest.raises(ValueError, match=r"top_pct"):
        compute_discrimination({1: {"A": 1}}, {"A": 10}, top_pct=0.6)


def test_discrimination_rejects_empty_cohort() -> None:
    with pytest.raises(ValueError, match=r"empty"):
        compute_discrimination({1: {}}, {}, top_pct=0.27)
