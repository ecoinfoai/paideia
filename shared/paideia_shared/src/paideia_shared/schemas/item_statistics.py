"""ItemStatistics: per-question CTT statistics + metadata (immersio Phase 1).

Phase 1 핵심 entity. 본 모델 1행 = ExamItem 1개 + 응시자 응답 집계.
무응답은 응시자 분모에 포함하되 오답으로 처리; 결시는 분모에서 제외 (research §R-04).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from ._common import CourseSlug, SemesterCode

DistractorLabel = Literal[
    "역변별 의심 — 출제 재검토",
    "모두 풀 수 있는 기본 문항",
    "어려운 변별 우수 문항(유지 권장)",
    "시간 부족 또는 포기형",
    "근접 distractor에 의한 변별 성공형",
    "변별 기여 적음 — 차년도 교체 검토",
    "특이사항 없음",
]


class ItemStatistics(BaseModel):
    """One row per exam item — CTT statistics + ExamItem passthrough metadata.

    Phase 1 핵심 entity (data-model.md §1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_no: int = Field(ge=1, description="문항 번호 1부터")
    semester: SemesterCode
    course_slug: CourseSlug

    chapter: str = Field(description="예: '1장. 서론'. ExamItem.chapter passthrough")
    week: int | None = Field(default=None, ge=1, description="주차")
    item_type: str = Field(description="예: '지식축적', '이해', '적용'")
    difficulty_level: int = Field(ge=1, le=5, description="출제자 의도 난이도")
    expected_difficulty: Literal["쉬움", "보통", "어려움"]
    source: Literal["형성평가", "교과서", "퀴즈", "기타"] = Field(description="문항 출처")
    correct_answer: int = Field(ge=1, le=5, description="정답 보기 번호")

    n_responders: int = Field(ge=0, description="응시자 수 (결시 제외)")
    n_correct: int = Field(ge=0, description="정답자 수")
    n_omit: int = Field(ge=0, description="무응답자 수")

    correct_rate: float = Field(ge=0.0, le=1.0, description="정답자/응시자, 무응답은 오답 처리")
    omit_rate: float = Field(ge=0.0, le=1.0, description="무응답/응시자")
    discrimination_index: float = Field(
        ge=-1.0, le=1.0, description="상위27% 정답률 - 하위27% 정답률"
    )
    point_biserial: float | None = Field(description="문항정오 × 총점 상관, NaN시 None")

    top_distractor_no: int | None = Field(default=None, ge=1, le=5, description="최다오답 번호")
    top_distractor_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    is_top_distractor_adjacent: bool = Field(description="최다오답이 정답 인접 보기인가")
    option_distribution: dict[int, float] = Field(description="{보기번호: 응답비율}, 합 ≤ 1.0")

    distractor_label: DistractorLabel

    @field_validator("n_correct")
    @classmethod
    def correct_le_responders(cls, v: int, info: ValidationInfo) -> int:
        """V1: n_correct ≤ n_responders."""
        if v > info.data.get("n_responders", 0):
            raise ValueError("ItemStatistics V1: n_correct > n_responders")
        return v

    @field_validator("n_omit")
    @classmethod
    def omit_le_responders(cls, v: int, info: ValidationInfo) -> int:
        """V2: n_omit ≤ n_responders."""
        if v > info.data.get("n_responders", 0):
            raise ValueError("ItemStatistics V2: n_omit > n_responders")
        return v

    @field_validator("option_distribution")
    @classmethod
    def distribution_sums(cls, v: dict[int, float]) -> dict[int, float]:
        """V3: option_distribution 합 ≤ 1.0001 (부동소수점 허용)."""
        total = sum(v.values())
        if total > 1.0001:
            raise ValueError(f"ItemStatistics V3: option_distribution sum {total} > 1.0")
        return v
