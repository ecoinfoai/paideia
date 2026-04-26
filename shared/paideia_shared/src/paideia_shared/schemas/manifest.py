"""IngestManifest and nested models for Silver sidecar metadata."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._common import CourseSlug, OutputKey, SemesterCode

_INPUT_ROLES_REQUIRED: frozenset[str] = frozenset(
    {
        "diagnostic_csv",
        "exam_omr_xls",
        "attendance_xlsx",
        "exam_yaml",
        "diagnostic_mapping_yaml",
    }
)
_PEP440_RELEASE_PATTERN = re.compile(r"^\d+(\.\d+)*([abc]\d+|rc\d+)?(\.post\d+)?(\.dev\d+)?$")


class IngestInput(BaseModel):
    """One Bronze input file (or mapping YAML) with provenance hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal[
        "diagnostic_csv",
        "exam_omr_xls",
        "attendance_xlsx",
        "exam_yaml",
        "diagnostic_mapping_yaml",
    ]
    path: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    encoding: Literal["utf-8", "cp949"] | None = None


class IngestRowCount(BaseModel):
    """Row counts of the four Silver Parquet outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_master: Annotated[int, Field(ge=0)]
    diagnostic_response: Annotated[int, Field(ge=0)]
    exam_result: Annotated[int, Field(ge=0)]
    exam_item: Annotated[int, Field(ge=0)]


class IngestManifest(BaseModel):
    """Sidecar manifest written alongside the four Silver Parquet outputs.

    Captures input provenance (sha256), mapping version, generation time,
    row-count summary, unrecognized-file list, and any new multiselect
    options encountered during this run, fulfilling spec FR-022 / FR-026.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_key: OutputKey
    semester: SemesterCode
    course_slug: CourseSlug
    course_name_kr: str | None = None
    paideia_shared_version: str
    immersio_version: str
    mapping_version: Annotated[int, Field(ge=1)]
    inputs: list[IngestInput]
    unrecognized_files: list[str] = Field(default_factory=list)
    multiselect_new_options: dict[str, list[str]] = Field(default_factory=dict)
    row_counts: IngestRowCount
    created_at: datetime
    git_commit: str | None = None

    @model_validator(mode="after")
    def v1_output_key_consistency(self) -> Self:
        """output_key must equal '{semester}-{course_slug}'."""
        expected = f"{self.semester}-{self.course_slug}"
        if self.output_key != expected:
            raise ValueError(
                f"IngestManifest V1: output_key={self.output_key!r} does not match "
                f"'{{semester}}-{{course_slug}}'={expected!r}."
            )
        return self

    @model_validator(mode="after")
    def v2_inputs_role_coverage(self) -> Self:
        """Inputs must contain each of the five required roles exactly once."""
        seen: list[str] = [item.role for item in self.inputs]
        seen_set = set(seen)
        if seen_set != set(_INPUT_ROLES_REQUIRED):
            missing = sorted(_INPUT_ROLES_REQUIRED - seen_set)
            extra = sorted(seen_set - _INPUT_ROLES_REQUIRED)
            raise ValueError(
                f"IngestManifest V2: inputs role coverage incomplete; "
                f"missing={missing}, unexpected={extra}."
            )
        for role in _INPUT_ROLES_REQUIRED:
            if seen.count(role) != 1:
                raise ValueError(
                    f"IngestManifest V2: role {role!r} appears {seen.count(role)} "
                    f"times in inputs; expected exactly 1."
                )
        return self

    @model_validator(mode="after")
    def v3_paideia_shared_version_pep440(self) -> Self:
        """paideia_shared_version must match a simple PEP 440 release pattern."""
        if not _PEP440_RELEASE_PATTERN.match(self.paideia_shared_version):
            raise ValueError(
                f"IngestManifest V3: paideia_shared_version="
                f"{self.paideia_shared_version!r} is not a valid PEP 440 release."
            )
        return self
