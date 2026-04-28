"""MetadataAggregate: per-(metadata_kind, metadata_value) group statistics.

xlsx `2_메타데이터통계` 시트 행 (data-model.md §3).
검정종류는 ANOVA / Welch ANOVA / Welch t-test / N/A 중 하나 — Levene 결과에 따라
서비스 단에서 자동 분기 (research §R-02).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MetadataKind = Literal[
    "분반",
    "고교생물_이수",
    "직업",
    "예상난이도",
    "난이도",
    "문제유형",
    "출처",
    "챕터",
]

TestKind = Literal["ANOVA", "Welch ANOVA", "Welch t-test", "N/A"]


class MetadataAggregate(BaseModel):
    """One row per (metadata_kind, metadata_value) — group-level statistics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata_kind: MetadataKind
    metadata_value: str = Field(
        description="예: 'A반', '예, 심화 과정까지 이수했습니다.', '쉬움'"
    )

    n: int = Field(ge=0, description="해당 그룹 응시자 수")
    mean: float | None = Field(default=None, description="평균 점수 또는 정답률")
    sd: float | None = Field(default=None, ge=0.0, description="표준편차")

    test_kind: TestKind = Field(description="해당 metadata_kind 그룹간 차이 검정 종류")
    test_p_value: float | None = Field(
        default=None, ge=0.0, le=1.0, description="검정 p값"
    )
    levene_p_value: float | None = Field(
        default=None, ge=0.0, le=1.0, description="등분산 검사 p값"
    )

    note: str | None = Field(default=None, description="예: '표본 < 30명, 신뢰도 낮음'")
