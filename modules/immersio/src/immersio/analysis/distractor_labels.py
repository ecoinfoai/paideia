"""label_distractor_pattern — 6 if-then 우선순위 룰 평가 (T039, FR-019).

Spec 004 research §R-07. 임계값은 ``analysis.ruleset`` 의 상수에서만 옴
(헌장 III: 변동성은 설정). 룰 변경 시 ``RULESET_VERSION`` 동시 bump.

Rule priority (highest → lowest):
    1. discrimination_index < DISCRIMINATION_NEGATIVE_THRESHOLD → 역변별
    2. correct_rate > EASY_CORRECT_RATE_THRESHOLD → 모두 풀이 가능
    3. correct_rate < HARD_CORRECT_RATE_CEILING AND
       discrimination_index > HARD_DISCRIMINATION_FLOOR → 어려운 변별 우수
    4. omit_rate > TIME_PRESSURE_OMIT_THRESHOLD → 시간 부족
    5. top_distractor_rate > ADJACENT_DISTRACTOR_RATE_THRESHOLD AND
       is_top_distractor_adjacent → 근접 distractor 변별 성공
    6. WEAK_CORRECT_RATE_LOW ≤ correct_rate ≤ WEAK_CORRECT_RATE_HIGH AND
       abs(discrimination_index) < WEAK_DISCRIMINATION_ABS_CEILING → 변별 기여 적음
    else → 특이사항 없음
"""

from __future__ import annotations

from paideia_shared.schemas import DistractorLabel

from .ruleset import (
    ADJACENT_DISTRACTOR_RATE_THRESHOLD,
    DISCRIMINATION_NEGATIVE_THRESHOLD,
    EASY_CORRECT_RATE_THRESHOLD,
    HARD_CORRECT_RATE_CEILING,
    HARD_DISCRIMINATION_FLOOR,
    TIME_PRESSURE_OMIT_THRESHOLD,
    WEAK_CORRECT_RATE_HIGH,
    WEAK_CORRECT_RATE_LOW,
    WEAK_DISCRIMINATION_ABS_CEILING,
)


def label_distractor_pattern(
    *,
    correct_rate: float,
    discrimination_index: float,
    omit_rate: float,
    top_distractor_rate: float,
    is_top_distractor_adjacent: bool,
) -> DistractorLabel:
    """Return one of the seven canonical distractor labels.

    All inputs are in [0, 1] except ``discrimination_index`` ∈ [-1, 1].
    The function is pure — no side effects, identical input ⇒ identical
    output.

    Args:
        correct_rate: Item correctness rate (0..1, omits counted as wrong).
        discrimination_index: Top 27% rate − bottom 27% rate (-1..1).
        omit_rate: Per-item blank-response rate (0..1).
        top_distractor_rate: Most-popular wrong-option rate (0..1).
        is_top_distractor_adjacent: Whether that wrong option is adjacent
            to the correct option (per ``compute_item_statistics``).

    Returns:
        One of the seven labels exposed by
        ``paideia_shared.schemas.DistractorLabel``.
    """
    if discrimination_index < DISCRIMINATION_NEGATIVE_THRESHOLD:
        return "역변별 의심 — 출제 재검토"
    if correct_rate > EASY_CORRECT_RATE_THRESHOLD:
        return "모두 풀 수 있는 기본 문항"
    if (
        correct_rate < HARD_CORRECT_RATE_CEILING
        and discrimination_index > HARD_DISCRIMINATION_FLOOR
    ):
        return "어려운 변별 우수 문항(유지 권장)"
    if omit_rate > TIME_PRESSURE_OMIT_THRESHOLD:
        return "시간 부족 또는 포기형"
    if top_distractor_rate > ADJACENT_DISTRACTOR_RATE_THRESHOLD and is_top_distractor_adjacent:
        return "근접 distractor에 의한 변별 성공형"
    if (
        WEAK_CORRECT_RATE_LOW <= correct_rate <= WEAK_CORRECT_RATE_HIGH
        and abs(discrimination_index) < WEAK_DISCRIMINATION_ABS_CEILING
    ):
        return "변별 기여 적음 — 차년도 교체 검토"
    return "특이사항 없음"
