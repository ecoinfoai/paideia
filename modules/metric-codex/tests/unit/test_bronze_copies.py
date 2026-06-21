"""T028/T057 — Unit tests for Bronze-copy loaders (RED first, then GREEN).

Tests for:
- load_blueprint: valid YAML → ExamenBlueprint
- load_blueprint: missing file / malformed / non-mapping / validation → LocatedInputError
- load_curriculum_map: valid YAML → CurriculumMap
- load_curriculum_map: missing / malformed / non-mapping / missing-field → LocatedInputError
- load_exam_spec: blueprint + curriculum semester/course_slug mismatch → LocatedInputError
- load_school_excel_map: valid minimal YAML → SchoolExcelMap
- load_school_excel_map: no score/attendance / missing student_id / extra field → error
- SchoolExcelMap: frozen → pydantic ValidationError on mutation

T057 (FR-026 / MC-U08): load_cluster_names own-Bronze loader —
- Valid cluster_names.json → dict[int, str]
- Missing file → LocatedInputError naming the file
- Non-object JSON (array) → LocatedInputError
- Non-integer key → LocatedInputError
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from metric_codex.errors import LocatedInputError
from metric_codex.ingest.bronze_copies import (
    SchoolExcelMap,
    load_blueprint,
    load_cluster_names,
    load_curriculum_map,
    load_exam_spec,
    load_school_excel_map,
)
from paideia_shared.schemas import CurriculumMap, ExamenBlueprint
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Minimal valid YAML content helpers
# ---------------------------------------------------------------------------

_VALID_BLUEPRINT_YAML = """\
semester: "2026-1"
course_slug: "anatomy"
exam_name: "2026-1학기 기말고사"
total_items: 45
chapters:
  - "Ch1 세포"
  - "Ch2 조직"
difficulty_targets:
  easy: 0.45
  medium: 0.35
  hard: 0.20
source_mix:
  formative: 15
  quiz: 15
  textbook: 15
quiz_target: 15
answer_key_balance: true
"""

_VALID_CURRICULUM_YAML = """\
semester: "2026-1"
course_slug: "anatomy"
entries:
  - week: 1
    chapter: "Ch1 세포"
    chapter_no: 1
    sections:
      - "1.1 개요"
  - week: 2
    chapter: "Ch2 조직"
    chapter_no: 2
    sections:
      - "2.1 상피조직"
"""

# Curriculum with mismatched key fields but otherwise valid — used to exercise
# the curriculum-side branches of load_exam_spec when the blueprint matches.
_CURRICULUM_WRONG_SEMESTER_YAML = """\
semester: "2025-2"
course_slug: "anatomy"
entries:
  - week: 1
    chapter: "Ch1 세포"
    chapter_no: 1
    sections:
      - "1.1 개요"
"""

_CURRICULUM_WRONG_COURSE_YAML = """\
semester: "2026-1"
course_slug: "physiology"
entries:
  - week: 1
    chapter: "Ch1 세포"
    chapter_no: 1
    sections:
      - "1.1 개요"
"""

_VALID_SCHOOL_EXCEL_MAP_YAML = """\
semester: "2026-1"
course_slug: "anatomy"
sheet: 0
header_row: 1
columns:
  student_id: "학번"
  name_kr: "이름"
  score_total: "총점"
"""

_SCHOOL_EXCEL_MAP_NO_SCORES_YAML = """\
semester: "2026-1"
course_slug: "anatomy"
columns:
  student_id: "학번"
"""

_SCHOOL_EXCEL_MAP_NO_STUDENT_ID_YAML = """\
semester: "2026-1"
course_slug: "anatomy"
columns:
  name_kr: "이름"
  score_total: "총점"
"""


# ---------------------------------------------------------------------------
# load_blueprint
# ---------------------------------------------------------------------------


def test_load_blueprint_valid(tmp_path: Path) -> None:
    """Valid blueprint.yaml returns a validated ExamenBlueprint."""
    p = tmp_path / "blueprint.yaml"
    p.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")

    result = load_blueprint(p)

    assert isinstance(result, ExamenBlueprint)
    assert result.semester == "2026-1"
    assert result.course_slug == "anatomy"
    assert result.total_items == 45


def test_load_blueprint_missing_file(tmp_path: Path) -> None:
    """Missing blueprint.yaml raises LocatedInputError."""
    p = tmp_path / "blueprint.yaml"
    with pytest.raises(LocatedInputError):
        load_blueprint(p)


def test_load_blueprint_missing_file_mentions_path(tmp_path: Path) -> None:
    """LocatedInputError for missing file includes the file path."""
    p = tmp_path / "blueprint.yaml"
    with pytest.raises(LocatedInputError) as exc_info:
        load_blueprint(p)
    assert "blueprint.yaml" in str(exc_info.value)


def test_load_blueprint_malformed_yaml(tmp_path: Path) -> None:
    """Malformed YAML in blueprint raises LocatedInputError."""
    p = tmp_path / "blueprint.yaml"
    p.write_text("semester: [\nbad yaml{{{\n", encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_blueprint(p)


def test_load_blueprint_non_mapping_yaml(tmp_path: Path) -> None:
    """Non-mapping YAML (e.g., a list) in blueprint raises LocatedInputError."""
    p = tmp_path / "blueprint.yaml"
    p.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_blueprint(p)


def test_load_blueprint_validation_failure(tmp_path: Path) -> None:
    """Blueprint with missing required fields raises LocatedInputError."""
    p = tmp_path / "blueprint.yaml"
    p.write_text("semester: '2026-1'\n", encoding="utf-8")  # missing many required fields
    with pytest.raises(LocatedInputError):
        load_blueprint(p)


# ---------------------------------------------------------------------------
# load_curriculum_map
# ---------------------------------------------------------------------------


def test_load_curriculum_map_valid(tmp_path: Path) -> None:
    """Valid curriculum_map.yaml returns a validated CurriculumMap."""
    p = tmp_path / "curriculum_map.yaml"
    p.write_text(_VALID_CURRICULUM_YAML, encoding="utf-8")

    result = load_curriculum_map(p)

    assert isinstance(result, CurriculumMap)
    assert result.semester == "2026-1"
    assert len(result.entries) == 2


def test_load_curriculum_map_missing_file(tmp_path: Path) -> None:
    """Missing curriculum_map.yaml raises LocatedInputError."""
    p = tmp_path / "curriculum_map.yaml"
    with pytest.raises(LocatedInputError):
        load_curriculum_map(p)


def test_load_curriculum_map_malformed_yaml(tmp_path: Path) -> None:
    """Malformed YAML in curriculum_map raises LocatedInputError."""
    p = tmp_path / "curriculum_map.yaml"
    p.write_text("entries: [\n{{broken\n", encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_curriculum_map(p)


def test_load_curriculum_map_non_mapping_yaml(tmp_path: Path) -> None:
    """Non-mapping YAML in curriculum_map raises LocatedInputError."""
    p = tmp_path / "curriculum_map.yaml"
    p.write_text("- entry1\n- entry2\n", encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_curriculum_map(p)


def test_load_curriculum_map_validation_failure(tmp_path: Path) -> None:
    """Curriculum with missing required fields raises LocatedInputError (I3a)."""
    p = tmp_path / "curriculum_map.yaml"
    p.write_text("semester: '2026-1'\n", encoding="utf-8")  # missing course_slug + entries
    with pytest.raises(LocatedInputError):
        load_curriculum_map(p)


# ---------------------------------------------------------------------------
# load_exam_spec (combined loader with cross-check)
# ---------------------------------------------------------------------------


def test_load_exam_spec_valid(tmp_path: Path) -> None:
    """load_exam_spec with matching keys returns (blueprint, curriculum) tuple."""
    bp = tmp_path / "blueprint.yaml"
    cm = tmp_path / "curriculum_map.yaml"
    bp.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")
    cm.write_text(_VALID_CURRICULUM_YAML, encoding="utf-8")

    blueprint, curriculum = load_exam_spec(bp, cm, semester="2026-1", course_slug="anatomy")

    assert isinstance(blueprint, ExamenBlueprint)
    assert isinstance(curriculum, CurriculumMap)


def test_load_exam_spec_semester_mismatch(tmp_path: Path) -> None:
    """load_exam_spec with wrong semester raises LocatedInputError (blueprint branch)."""
    bp = tmp_path / "blueprint.yaml"
    cm = tmp_path / "curriculum_map.yaml"
    bp.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")
    cm.write_text(_VALID_CURRICULUM_YAML, encoding="utf-8")

    with pytest.raises(LocatedInputError):
        load_exam_spec(bp, cm, semester="2025-2", course_slug="anatomy")


def test_load_exam_spec_course_slug_mismatch(tmp_path: Path) -> None:
    """load_exam_spec with wrong course_slug raises LocatedInputError (blueprint branch)."""
    bp = tmp_path / "blueprint.yaml"
    cm = tmp_path / "curriculum_map.yaml"
    bp.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")
    cm.write_text(_VALID_CURRICULUM_YAML, encoding="utf-8")

    with pytest.raises(LocatedInputError):
        load_exam_spec(bp, cm, semester="2026-1", course_slug="physiology")


def test_load_exam_spec_curriculum_semester_mismatch(tmp_path: Path) -> None:
    """Blueprint matches but curriculum semester differs → LocatedInputError (I3b)."""
    bp = tmp_path / "blueprint.yaml"
    cm = tmp_path / "curriculum_map.yaml"
    bp.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")
    cm.write_text(_CURRICULUM_WRONG_SEMESTER_YAML, encoding="utf-8")

    with pytest.raises(LocatedInputError) as exc_info:
        load_exam_spec(bp, cm, semester="2026-1", course_slug="anatomy")
    # The error must point at the curriculum file, not the blueprint.
    assert "curriculum_map.yaml" in str(exc_info.value)


def test_load_exam_spec_curriculum_course_slug_mismatch(tmp_path: Path) -> None:
    """Blueprint matches but curriculum course_slug differs → LocatedInputError (I3b)."""
    bp = tmp_path / "blueprint.yaml"
    cm = tmp_path / "curriculum_map.yaml"
    bp.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")
    cm.write_text(_CURRICULUM_WRONG_COURSE_YAML, encoding="utf-8")

    with pytest.raises(LocatedInputError) as exc_info:
        load_exam_spec(bp, cm, semester="2026-1", course_slug="anatomy")
    assert "curriculum_map.yaml" in str(exc_info.value)


# ---------------------------------------------------------------------------
# load_school_excel_map
# ---------------------------------------------------------------------------


def test_load_school_excel_map_valid(tmp_path: Path) -> None:
    """Valid 성적출석_map.yaml returns a SchoolExcelMap instance."""
    p = tmp_path / "성적출석_map.yaml"
    p.write_text(_VALID_SCHOOL_EXCEL_MAP_YAML, encoding="utf-8")

    result = load_school_excel_map(p)

    assert isinstance(result, SchoolExcelMap)
    assert result.semester == "2026-1"
    assert result.course_slug == "anatomy"
    assert result.columns.student_id == "학번"
    assert result.columns.score_total == "총점"


def test_load_school_excel_map_defaults(tmp_path: Path) -> None:
    """SchoolExcelMap uses correct defaults for sheet and header_row."""
    p = tmp_path / "map.yaml"
    p.write_text(_VALID_SCHOOL_EXCEL_MAP_YAML, encoding="utf-8")
    result = load_school_excel_map(p)

    assert result.sheet == 0
    assert result.header_row == 1


def test_load_school_excel_map_missing_file(tmp_path: Path) -> None:
    """Missing 성적출석_map.yaml raises LocatedInputError."""
    p = tmp_path / "성적출석_map.yaml"
    with pytest.raises(LocatedInputError):
        load_school_excel_map(p)


def test_load_school_excel_map_no_scores_raises(tmp_path: Path) -> None:
    """SchoolExcelMap without any score/attendance column raises LocatedInputError."""
    p = tmp_path / "map.yaml"
    p.write_text(_SCHOOL_EXCEL_MAP_NO_SCORES_YAML, encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_school_excel_map(p)


def test_load_school_excel_map_no_student_id_raises(tmp_path: Path) -> None:
    """ColumnMap without student_id raises LocatedInputError (wrapped ValidationError)."""
    p = tmp_path / "map.yaml"
    p.write_text(_SCHOOL_EXCEL_MAP_NO_STUDENT_ID_YAML, encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_school_excel_map(p)


def test_load_school_excel_map_extra_fields_forbidden(tmp_path: Path) -> None:
    """Extra fields in the YAML raise LocatedInputError (extra='forbid')."""
    p = tmp_path / "map.yaml"
    p.write_text(
        _VALID_SCHOOL_EXCEL_MAP_YAML + "unexpected_field: value\n",
        encoding="utf-8",
    )
    with pytest.raises(LocatedInputError):
        load_school_excel_map(p)


def test_load_school_excel_map_cohort_year_column_optional(tmp_path: Path) -> None:
    """cohort_year_column defaults to None when absent."""
    p = tmp_path / "map.yaml"
    p.write_text(_VALID_SCHOOL_EXCEL_MAP_YAML, encoding="utf-8")
    result = load_school_excel_map(p)
    assert result.cohort_year_column is None


def test_load_school_excel_map_cohort_year_column_set(tmp_path: Path) -> None:
    """cohort_year_column is parsed when provided."""
    yaml_content = _VALID_SCHOOL_EXCEL_MAP_YAML + 'cohort_year_column: "입학년도"\n'
    p = tmp_path / "map.yaml"
    p.write_text(yaml_content, encoding="utf-8")
    result = load_school_excel_map(p)
    assert result.cohort_year_column == "입학년도"


def test_load_school_excel_map_attendance_column(tmp_path: Path) -> None:
    """attendance column is recognized as a valid score/attendance signal."""
    yaml_content = """\
semester: "2026-1"
course_slug: "anatomy"
columns:
  student_id: "학번"
  attendance: "출석"
"""
    p = tmp_path / "map.yaml"
    p.write_text(yaml_content, encoding="utf-8")
    result = load_school_excel_map(p)
    assert result.columns.attendance == "출석"


def test_school_excel_map_is_frozen(tmp_path: Path) -> None:
    """SchoolExcelMap is frozen: mutation raises pydantic ValidationError."""
    p = tmp_path / "map.yaml"
    p.write_text(_VALID_SCHOOL_EXCEL_MAP_YAML, encoding="utf-8")
    result = load_school_excel_map(p)

    with pytest.raises(ValidationError):
        result.sheet = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LocatedInputError is ValueError (CLI exit-2 trap via bronze_copies path)
# ---------------------------------------------------------------------------


def test_located_input_error_from_bronze_is_value_error(tmp_path: Path) -> None:
    """LocatedInputError from bronze loaders is catchable as ValueError."""
    p = tmp_path / "blueprint.yaml"
    with pytest.raises(ValueError):
        load_blueprint(p)

    assert issubclass(LocatedInputError, ValueError)


# ---------------------------------------------------------------------------
# T057 (FR-026 / MC-U08) — load_cluster_names own-Bronze loader
# ---------------------------------------------------------------------------


def test_load_cluster_names_valid(tmp_path: Path) -> None:
    """Valid cluster_names.json returns a dict[int, str]."""
    p = tmp_path / "cluster_names.json"
    p.write_text(json.dumps({"0": "성실형", "1": "도전형"}), encoding="utf-8")

    result = load_cluster_names(p)

    assert result == {0: "성실형", 1: "도전형"}


def test_load_cluster_names_missing_file_raises(tmp_path: Path) -> None:
    """Missing cluster_names.json raises LocatedInputError naming the file."""
    p = tmp_path / "cluster_names.json"
    with pytest.raises(LocatedInputError) as exc_info:
        load_cluster_names(p)
    assert "cluster_names.json" in str(exc_info.value)


def test_load_cluster_names_non_object_raises(tmp_path: Path) -> None:
    """A JSON array (not object) raises LocatedInputError."""
    p = tmp_path / "cluster_names.json"
    p.write_text(json.dumps(["성실형", "도전형"]), encoding="utf-8")
    with pytest.raises(LocatedInputError) as exc_info:
        load_cluster_names(p)
    assert "cluster_names.json" in str(exc_info.value)


def test_load_cluster_names_non_integer_key_raises(tmp_path: Path) -> None:
    """A key that cannot be coerced to int raises LocatedInputError."""
    p = tmp_path / "cluster_names.json"
    p.write_text(json.dumps({"abc": "성실형"}), encoding="utf-8")
    with pytest.raises(LocatedInputError) as exc_info:
        load_cluster_names(p)
    assert "cluster_names.json" in str(exc_info.value)
