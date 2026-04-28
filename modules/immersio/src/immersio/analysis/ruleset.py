"""Distractor-pattern label rule thresholds (immersio Phase 1, FR-019/FR-020).

Spec 004 research §R-07 — 6 if-then 우선순위 평가에 쓰이는 임계값 + 룰셋 버전.

임계값 변경 시 RULESET_VERSION 을 SemVer-bump 하고
``shared.paideia_shared.schemas.immersio_phase1_manifest.ImmersioPhase1Manifest``
의 ``ruleset_version`` Literal 도 동일하게 갱신해야 한다 (FR-020).
"""

from __future__ import annotations

from typing import Final

RULESET_VERSION: Final[str] = "1.0.0"
"""Semantic version of the distractor-label ruleset.

Bump this whenever any threshold below changes. The version is recorded in
each run's manifest (``ImmersioPhase1Manifest.ruleset_version``) so two
analyses can be compared with provenance.
"""

# 1) 역변별 의심 — 변별력이 음수
DISCRIMINATION_NEGATIVE_THRESHOLD: Final[float] = 0.0
"""``discrimination_index < DISCRIMINATION_NEGATIVE_THRESHOLD`` → '역변별 의심'."""

# 2) 모두 풀 수 있는 기본 문항 — 정답률이 매우 높음
EASY_CORRECT_RATE_THRESHOLD: Final[float] = 0.95
"""``correct_rate > EASY_CORRECT_RATE_THRESHOLD`` → '모두 풀 수 있는 기본 문항'."""

# 3) 어려운 변별 우수 문항 — 정답률 낮으면서 변별력 우수
HARD_CORRECT_RATE_CEILING: Final[float] = 0.30
HARD_DISCRIMINATION_FLOOR: Final[float] = 0.30
"""``correct_rate < HARD_CORRECT_RATE_CEILING`` AND
``discrimination_index > HARD_DISCRIMINATION_FLOOR`` → '어려운 변별 우수 문항(유지 권장)'.
"""

# 4) 시간 부족 또는 포기형 — 무응답률 높음
TIME_PRESSURE_OMIT_THRESHOLD: Final[float] = 0.10
"""``omit_rate > TIME_PRESSURE_OMIT_THRESHOLD`` → '시간 부족 또는 포기형'."""

# 5) 근접 distractor 변별 성공형 — 인접 오답이 정답 인접에 몰려 있음
ADJACENT_DISTRACTOR_RATE_THRESHOLD: Final[float] = 0.30
"""``top_distractor_rate > ADJACENT_DISTRACTOR_RATE_THRESHOLD`` AND
``is_top_distractor_adjacent`` → '근접 distractor에 의한 변별 성공형'.
"""

# 6) 변별 기여 적음 — 중간 정답률 + 낮은 변별력 (절대값)
WEAK_CORRECT_RATE_LOW: Final[float] = 0.50
WEAK_CORRECT_RATE_HIGH: Final[float] = 0.80
WEAK_DISCRIMINATION_ABS_CEILING: Final[float] = 0.10
"""``WEAK_CORRECT_RATE_LOW <= correct_rate <= WEAK_CORRECT_RATE_HIGH`` AND
``abs(discrimination_index) < WEAK_DISCRIMINATION_ABS_CEILING`` →
'변별 기여 적음 — 차년도 교체 검토'.
"""

__all__ = [
    "RULESET_VERSION",
    "DISCRIMINATION_NEGATIVE_THRESHOLD",
    "EASY_CORRECT_RATE_THRESHOLD",
    "HARD_CORRECT_RATE_CEILING",
    "HARD_DISCRIMINATION_FLOOR",
    "TIME_PRESSURE_OMIT_THRESHOLD",
    "ADJACENT_DISTRACTOR_RATE_THRESHOLD",
    "WEAK_CORRECT_RATE_LOW",
    "WEAK_CORRECT_RATE_HIGH",
    "WEAK_DISCRIMINATION_ABS_CEILING",
]
