"""ImmersioPhase1Manifest: per-run audit metadata for immersio Phase 1+2.

silver `manifest.json` 과 gold `manifest.json` 동일 구조 (data-model.md §6).
schema_version 변경 시 본 spec 의 ruleset_version 또는 데이터 모델 변경 동반.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, SemesterCode


class ImmersioPhase1Manifest(BaseModel):
    """Per-run audit metadata for immersio Phase 1+2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    semester: SemesterCode
    course_slug: CourseSlug
    generated_at_utc: str = Field(description="ISO 8601, hash-derived 시각 (research §R-10)")

    exam_item_yaml_sha256: str = Field(description="ExamItem yaml sha256")
    omr_xls_sha256_list: list[str] = Field(description="분반별 OMR xls sha256 리스트 (정렬됨)")
    attendance_sha256: str = Field(description="출석부 xlsx sha256")
    needs_map_silver_sha256: str | None = Field(
        default=None, description="needs-map silver 전체 디렉터리 hash, 없으면 None"
    )

    run_seed: int = Field(description="난수 시드 (PAIDEIA_RANDOM_SEED 또는 default 42)")
    ruleset_version: Literal["1.0.0"] = Field(
        default="1.0.0", description="오답 라벨 룰 버전 (FR-020)"
    )

    total_items: int = Field(ge=0, description="ExamItem 수")
    total_responders: int = Field(ge=0, description="응시자 수 (결시 제외)")
    total_absent: int = Field(ge=0, description="결시자 수")
    total_omit_responses: int = Field(ge=0, description="무응답 응답 수 (학생 × 문항)")

    silver_outputs: dict[str, str] = Field(description="{name: relative path}")
    gold_outputs: dict[str, str] = Field(description="{name: relative path}")

    legacy_diff_total_cells: int = Field(ge=0, description="legacy 와 비교한 셀 수")
    legacy_diff_diff_cells: int = Field(ge=0, description="차이가 발견된 셀 수")
    legacy_diff_immersio_chose_count: int = Field(ge=0, description="immersio 채택 결정 수")

    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def diff_consistency(self) -> ImmersioPhase1Manifest:
        """V1: legacy_diff_diff_cells ≤ legacy_diff_total_cells."""
        if self.legacy_diff_diff_cells > self.legacy_diff_total_cells:
            raise ValueError("ImmersioPhase1Manifest V1: diff cells > total cells")
        return self
