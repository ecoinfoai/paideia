"""Unit tests for label_distractor_pattern (T029).

Spec 004 research §R-07 — 6 if-then 우선순위 평가:
1. discrimination_index < 0 → '역변별 의심 — 출제 재검토'
2. correct_rate > 0.95 → '모두 풀 수 있는 기본 문항'
3. correct_rate < 0.30 AND discrimination_index > 0.30 → '어려운 변별 우수 문항(유지 권장)'
4. omit_rate > 0.10 → '시간 부족 또는 포기형'
5. top_distractor_rate > 0.30 AND is_top_distractor_adjacent → '근접 distractor에 의한 변별 성공형'
6. 0.50 ≤ correct_rate ≤ 0.80 AND abs(discrimination_index) < 0.10 → '변별 기여 적음 — 차년도 교체 검토'
else → '특이사항 없음'

label_distractor_pattern 은 ``(correct_rate, discrimination_index, omit_rate,
top_distractor_rate, is_top_distractor_adjacent)`` 5개 인자를 받음.
"""

from __future__ import annotations

import pytest

from immersio.analysis.distractor_labels import label_distractor_pattern


def _label(
    *,
    correct_rate: float,
    discrimination_index: float,
    omit_rate: float = 0.0,
    top_distractor_rate: float = 0.0,
    is_top_distractor_adjacent: bool = False,
) -> str:
    return label_distractor_pattern(
        correct_rate=correct_rate,
        discrimination_index=discrimination_index,
        omit_rate=omit_rate,
        top_distractor_rate=top_distractor_rate,
        is_top_distractor_adjacent=is_top_distractor_adjacent,
    )


# =====================================================================
# Rule 1 — 역변별 (highest priority)
# =====================================================================


def test_rule1_negative_discrimination() -> None:
    assert _label(correct_rate=0.5, discrimination_index=-0.001) == "역변별 의심 — 출제 재검토"


def test_rule1_zero_discrimination_does_not_trigger() -> None:
    """boundary: D == 0.0 은 음수 아님 → rule 1 미적용."""
    out = _label(correct_rate=0.6, discrimination_index=0.0)
    assert out != "역변별 의심 — 출제 재검토"


def test_rule1_priority_over_easy() -> None:
    """correct_rate > 0.95 + D < 0 → rule 1 우선."""
    assert _label(correct_rate=0.99, discrimination_index=-0.05) == "역변별 의심 — 출제 재검토"


# =====================================================================
# Rule 2 — 모두 풀 수 있는 기본 문항
# =====================================================================


def test_rule2_correct_rate_above_95() -> None:
    assert (
        _label(correct_rate=0.96, discrimination_index=0.1)
        == "모두 풀 수 있는 기본 문항"
    )


def test_rule2_correct_rate_eq_95_boundary() -> None:
    """boundary: correct_rate == 0.95 → rule 2 미적용 (strict >)."""
    out = _label(correct_rate=0.95, discrimination_index=0.1)
    assert out != "모두 풀 수 있는 기본 문항"


# =====================================================================
# Rule 3 — 어려운 변별 우수 문항
# =====================================================================


def test_rule3_low_correct_high_discrimination() -> None:
    assert (
        _label(correct_rate=0.25, discrimination_index=0.31)
        == "어려운 변별 우수 문항(유지 권장)"
    )


def test_rule3_boundary_correct_eq_30_does_not_trigger() -> None:
    """correct_rate == 0.30 → rule 3 미적용 (strict <)."""
    out = _label(correct_rate=0.30, discrimination_index=0.40)
    assert out != "어려운 변별 우수 문항(유지 권장)"


def test_rule3_boundary_discrimination_eq_30_does_not_trigger() -> None:
    """D == 0.30 → rule 3 미적용 (strict >)."""
    out = _label(correct_rate=0.20, discrimination_index=0.30)
    assert out != "어려운 변별 우수 문항(유지 권장)"


# =====================================================================
# Rule 4 — 시간 부족 또는 포기형
# =====================================================================


def test_rule4_high_omit_rate() -> None:
    assert (
        _label(correct_rate=0.50, discrimination_index=0.10, omit_rate=0.15)
        == "시간 부족 또는 포기형"
    )


def test_rule4_boundary_omit_eq_10_does_not_trigger() -> None:
    """omit == 0.10 → rule 4 미적용 (strict >)."""
    out = _label(correct_rate=0.65, discrimination_index=0.20, omit_rate=0.10)
    assert out != "시간 부족 또는 포기형"


# =====================================================================
# Rule 5 — 근접 distractor 변별 성공형
# =====================================================================


def test_rule5_adjacent_top_distractor_high() -> None:
    assert (
        _label(
            correct_rate=0.55,
            discrimination_index=0.35,
            top_distractor_rate=0.35,
            is_top_distractor_adjacent=True,
        )
        == "근접 distractor에 의한 변별 성공형"
    )


def test_rule5_non_adjacent_does_not_trigger() -> None:
    out = _label(
        correct_rate=0.55,
        discrimination_index=0.35,
        top_distractor_rate=0.35,
        is_top_distractor_adjacent=False,
    )
    assert out != "근접 distractor에 의한 변별 성공형"


# =====================================================================
# Rule 6 — 변별 기여 적음
# =====================================================================


def test_rule6_mid_correct_low_discrimination() -> None:
    assert (
        _label(correct_rate=0.65, discrimination_index=0.05)
        == "변별 기여 적음 — 차년도 교체 검토"
    )


def test_rule6_boundary_correct_eq_50() -> None:
    assert (
        _label(correct_rate=0.50, discrimination_index=0.05)
        == "변별 기여 적음 — 차년도 교체 검토"
    )


def test_rule6_boundary_correct_eq_80() -> None:
    assert (
        _label(correct_rate=0.80, discrimination_index=0.05)
        == "변별 기여 적음 — 차년도 교체 검토"
    )


def test_rule6_boundary_d_abs_eq_10_does_not_trigger() -> None:
    """abs(D) == 0.10 → rule 6 미적용 (strict <)."""
    out = _label(correct_rate=0.65, discrimination_index=0.10)
    assert out != "변별 기여 적음 — 차년도 교체 검토"


# =====================================================================
# Default — 특이사항 없음
# =====================================================================


def test_default_no_match() -> None:
    """변별력 좋고 정답률 적당, omit 낮음, 인접 distractor 없음."""
    assert (
        _label(correct_rate=0.40, discrimination_index=0.20, omit_rate=0.02)
        == "특이사항 없음"
    )


# =====================================================================
# Priority ordering — multiple rules match
# =====================================================================


def test_priority_rule3_beats_rule6() -> None:
    """correct_rate=0.25, D=0.40 — rule 3 우선 (rule 6 의 0.50-0.80 영역 밖이지만 보장)."""
    assert (
        _label(correct_rate=0.25, discrimination_index=0.40)
        == "어려운 변별 우수 문항(유지 권장)"
    )


def test_priority_rule4_beats_rule5() -> None:
    """omit_rate=0.20 도 만족 + 인접 distractor 도 만족 → rule 4 우선."""
    out = _label(
        correct_rate=0.55,
        discrimination_index=0.35,
        omit_rate=0.20,
        top_distractor_rate=0.35,
        is_top_distractor_adjacent=True,
    )
    assert out == "시간 부족 또는 포기형"
