"""T028 — Bronze-copy loaders for metric-codex.

metric-codex does NOT read another module's Silver/Gold for the exam
specification: examen never persists blueprint/curriculum to Silver.
Instead the professor places copies under metric-codex's own Bronze tier:

- ``data/bronze/metric-codex/{key}/blueprint.yaml``      → ExamenBlueprint
- ``data/bronze/metric-codex/{key}/curriculum_map.yaml`` → CurriculumMap
- ``data/bronze/metric-codex/{key}/成績出席_map.yaml``     → SchoolExcelMap
- ``data/bronze/metric-codex/{key}/cluster_names.json``  → dict[int, str]

The cluster_names.json own-copy is the Principle-II own-Bronze copy: needs-map
does not guarantee a stable Silver-side sidecar, so metric-codex keeps its own
authoritative copy under Bronze (FR-026 / MC-U08).

Mirrors ``modules/retro-mester/src/retro_mester/load/examen.py`` but raises
``LocatedInputError`` (not retro's ``InputError``) throughout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Self

from paideia_shared.schemas import (
    CourseSlug,
    CurriculumMap,
    ExamenBlueprint,
    SemesterCode,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from metric_codex.errors import LocatedInputError
from metric_codex.yaml_load import load_yaml_mapping

# ---------------------------------------------------------------------------
# SchoolExcelMap — config that maps school Excel columns to ingest fields
# ---------------------------------------------------------------------------


class ColumnMap(BaseModel):
    """Mapping from canonical field names to header strings in the Excel file.

    At least one of ``score_total``, ``score_percent``, or ``attendance`` must
    be present (enforced by ``SchoolExcelMap._v_at_least_one_signal``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: str = Field(..., description="Header text for the student-ID column (학번).")
    name_kr: str | None = Field(None, description="Header text for the Korean name column.")
    score_total: str | None = Field(None, description="Header text for the total-score column.")
    score_percent: str | None = Field(
        None, description="Header text for the percentage-score column."
    )
    attendance: str | None = Field(None, description="Header text for the attendance column.")


class SchoolExcelMap(BaseModel):
    """Config mapping school Excel columns to metric-codex ingest fields.

    Parsed from ``성적출석_map.yaml`` in metric-codex's own Bronze tier.

    Invariant: at least one of ``columns.score_total``, ``columns.score_percent``,
    or ``columns.attendance`` must be non-None (the source must carry at least
    one score/attendance signal — enforced by V1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    semester: SemesterCode
    course_slug: CourseSlug
    sheet: str | int = Field(0, description="Sheet name or 0-based index (default 0).")
    header_row: Annotated[int, Field(ge=1)] = Field(
        1, description="1-based row number holding column headers (default 1)."
    )
    columns: ColumnMap
    cohort_year_column: str | None = Field(
        None,
        description=(
            "Header text of the column holding the cohort year.  When None, "
            "cohort_year is derived from the first 4 digits of the normalized 학번."
        ),
    )

    @model_validator(mode="after")
    def _v1_at_least_one_signal(self) -> Self:
        """V1: at least one of score_total / score_percent / attendance must be set."""
        cols = self.columns
        if cols.score_total is None and cols.score_percent is None and cols.attendance is None:
            raise ValueError(
                "V1: columns must specify at least one of 'score_total', "
                "'score_percent', or 'attendance' — a source layer must carry "
                "at least one score or attendance signal."
            )
        return self


# ---------------------------------------------------------------------------
# load_blueprint
# ---------------------------------------------------------------------------


def load_blueprint(path: Path) -> ExamenBlueprint:
    """Load and validate ``blueprint.yaml`` from metric-codex's Bronze tier.

    Args:
        path: Absolute path to the blueprint.yaml file.

    Returns:
        Validated ExamenBlueprint instance.

    Raises:
        LocatedInputError: If the file does not exist, YAML parsing fails,
            the content is not a mapping, or Pydantic validation fails.
    """
    raw = load_yaml_mapping(path, "blueprint.yaml")
    try:
        return ExamenBlueprint(**raw)
    except ValidationError as exc:
        raise LocatedInputError(
            f"blueprint.yaml validation failed: {exc}",
            file=str(path),
        ) from exc


# ---------------------------------------------------------------------------
# load_curriculum_map
# ---------------------------------------------------------------------------


def load_curriculum_map(path: Path) -> CurriculumMap:
    """Load and validate ``curriculum_map.yaml`` from metric-codex's Bronze tier.

    Args:
        path: Absolute path to the curriculum_map.yaml file.

    Returns:
        Validated CurriculumMap instance.

    Raises:
        LocatedInputError: If the file does not exist, YAML parsing fails,
            the content is not a mapping, or Pydantic validation fails.
    """
    raw = load_yaml_mapping(path, "curriculum_map.yaml")
    try:
        return CurriculumMap(**raw)
    except ValidationError as exc:
        raise LocatedInputError(
            f"curriculum_map.yaml validation failed: {exc}",
            file=str(path),
        ) from exc


# ---------------------------------------------------------------------------
# load_school_excel_map
# ---------------------------------------------------------------------------


def load_school_excel_map(path: Path) -> SchoolExcelMap:
    """Load and validate ``성적출석_map.yaml`` from metric-codex's Bronze tier.

    Args:
        path: Absolute path to the 성적출석_map.yaml file.

    Returns:
        Validated SchoolExcelMap instance.

    Raises:
        LocatedInputError: If the file does not exist, YAML parsing fails,
            the content is not a mapping, or Pydantic validation fails
            (including the V1 at-least-one-signal invariant).
    """
    raw = load_yaml_mapping(path, "성적출석_map.yaml")
    try:
        return SchoolExcelMap(**raw)
    except ValidationError as exc:
        raise LocatedInputError(
            f"성적출석_map.yaml validation failed: {exc}",
            file=str(path),
        ) from exc


# ---------------------------------------------------------------------------
# load_exam_spec (combined loader with key cross-check)
# ---------------------------------------------------------------------------


def load_exam_spec(
    blueprint_path: Path,
    curriculum_map_path: Path,
    semester: str,
    course_slug: str,
) -> tuple[ExamenBlueprint, CurriculumMap]:
    """Load the blueprint + curriculum pair and cross-check the semester/course key.

    Args:
        blueprint_path: Path to ``blueprint.yaml`` (metric-codex Bronze).
        curriculum_map_path: Path to ``curriculum_map.yaml`` (metric-codex Bronze).
        semester: Expected semester code (e.g. ``"2026-1"``).
        course_slug: Expected course slug (e.g. ``"anatomy"``).

    Returns:
        A ``(blueprint, curriculum_map)`` tuple of validated Pydantic instances.

    Raises:
        LocatedInputError: If either file is missing/malformed, Pydantic
            validation fails, or the loaded ``semester``/``course_slug`` does
            not match the requested key.
    """
    blueprint = load_blueprint(blueprint_path)
    curriculum = load_curriculum_map(curriculum_map_path)

    if blueprint.semester != semester:
        raise LocatedInputError(
            f"semester mismatch: expected '{semester}', got '{blueprint.semester}'",
            file=str(blueprint_path),
        )
    if blueprint.course_slug != course_slug:
        raise LocatedInputError(
            f"course_slug mismatch: expected '{course_slug}', got '{blueprint.course_slug}'",
            file=str(blueprint_path),
        )
    if curriculum.semester != semester:
        raise LocatedInputError(
            f"semester mismatch: expected '{semester}', got '{curriculum.semester}'",
            file=str(curriculum_map_path),
        )
    if curriculum.course_slug != course_slug:
        raise LocatedInputError(
            f"course_slug mismatch: expected '{course_slug}', got '{curriculum.course_slug}'",
            file=str(curriculum_map_path),
        )

    return blueprint, curriculum


# ---------------------------------------------------------------------------
# load_cluster_names — own-Bronze copy (FR-026 / MC-U08)
# ---------------------------------------------------------------------------


def load_cluster_names(path: Path) -> dict[int, str]:
    """Load ``cluster_names.json`` from metric-codex's own Bronze tier.

    metric-codex keeps its own copy of cluster_names.json under Bronze because
    the needs-map Silver sidecar is not guaranteed to be present in production.
    This loader is the canonical Bronze-tier reader for that file (Principle II).

    JSON object keys are strings; they are coerced to ints (the cluster ids).

    Args:
        path: Absolute path to ``cluster_names.json`` in metric-codex Bronze.

    Returns:
        Mapping of cluster_id (int) → label (str).

    Raises:
        LocatedInputError: If the file does not exist, is not valid JSON, is not
            a JSON object, or has a key that cannot be coerced to int.
    """
    if not path.is_file():
        raise LocatedInputError(
            f"cluster_names.json not found at {path}",
            file=path.name,
            expected="cluster_names.json in metric-codex Bronze tier",
            actual="(file absent)",
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LocatedInputError(
            f"failed to parse cluster names JSON: {exc}",
            file=path.name,
        ) from exc
    if not isinstance(raw, dict):
        raise LocatedInputError(
            "cluster_names.json must be a JSON object mapping cluster_id → label",
            file=path.name,
            expected="object mapping cluster_id → label",
            actual=type(raw).__name__,
        )
    names: dict[int, str] = {}
    for key, label in raw.items():
        try:
            cluster_id = int(key)
        except (TypeError, ValueError) as exc:
            raise LocatedInputError(
                f"non-integer cluster id key {key!r} in cluster_names.json",
                file=path.name,
                expected="integer cluster id key",
                actual=repr(key),
            ) from exc
        names[cluster_id] = str(label)
    return names


__all__ = [
    "ColumnMap",
    "SchoolExcelMap",
    "load_blueprint",
    "load_cluster_names",
    "load_curriculum_map",
    "load_school_excel_map",
    "load_exam_spec",
]
