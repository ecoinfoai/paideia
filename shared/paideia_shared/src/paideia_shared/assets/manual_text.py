"""ManualTextAsset — Pydantic schema for the v0.1.1 operator manual asset.

Validates ``shared/paideia_shared/src/paideia_shared/assets/manual_text.ko.yaml``
(authored by T045). The structure mirrors data-model.md "매뉴얼 자산 데이터
모델" section.

Operators edit the YAML asset only; pipeline code (T047 ``render_manual_pdf``)
walks the validated tree and emits a deterministic reportlab PDF without
re-running any LLM. This keeps the manual byte-equal across pipeline reruns
when the YAML and figure assets are unchanged (FR-035, SC-005).

Spec: 003-needs-map-v0-1-1/data-model.md §"매뉴얼 자산 데이터 모델" + spec
      FR-023/FR-024.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ManualMetadata(BaseModel):
    """Metadata block at the top of the manual YAML asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    language: Annotated[str, Field(min_length=2, max_length=8)]
    schema_version: Annotated[str, Field(min_length=1)]
    last_updated: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class ManualAxisEntry(BaseModel):
    """One quantitative-axis entry inside the 8-axes section."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")]
    name_kr: Annotated[str, Field(min_length=1)]
    meaning: Annotated[str, Field(min_length=1)]
    example_items: list[str] = Field(default_factory=list)
    operating_use: Annotated[str, Field(min_length=1)]


class ManualGroupEntry(BaseModel):
    """One auxiliary-group entry inside the 3-groups section."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")]
    name_kr: Annotated[str, Field(min_length=1)]
    meaning: Annotated[str, Field(min_length=1)]
    options_or_examples: list[str] = Field(default_factory=list)
    operating_use: Annotated[str, Field(min_length=1)]


class ManualSection(BaseModel):
    """One top-level section of the manual."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    title: Annotated[str, Field(min_length=1)]
    body_paragraphs: list[str] = Field(default_factory=list)
    figure_ref: str | None = None
    axis_entries: list[ManualAxisEntry] = Field(default_factory=list)
    group_entries: list[ManualGroupEntry] = Field(default_factory=list)


class ManualTextAsset(BaseModel):
    """Full manual asset — one YAML file under ``assets/manual_text.{lang}.yaml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: ManualMetadata
    sections: Annotated[list[ManualSection], Field(min_length=1)]
