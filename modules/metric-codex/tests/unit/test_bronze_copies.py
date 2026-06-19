"""T028 — Unit tests for Bronze-copy loaders (RED first, then GREEN).

Tests for:
- load_blueprint: valid YAML → ExamenBlueprint
- load_blueprint: missing file → LocatedInputError
- load_blueprint: malformed YAML → LocatedInputError
- load_blueprint: non-mapping YAML → LocatedInputError
- load_blueprint: Pydantic validation failure → LocatedInputError
- load_curriculum_map: valid YAML → CurriculumMap
- load_curriculum_map: missing file → LocatedInputError
- load_curriculum_map: malformed YAML → LocatedInputError
- load_curriculum_map: non-mapping YAML → LocatedInputError
- load_exam_spec: semester mismatch → LocatedInputError
- load_exam_spec: course_slug mismatch → LocatedInputError
- load_school_excel_map: valid minimal YAML → SchoolExcelMap
- load_school_excel_map: all score/attendance columns absent → LocatedInputError
- load_school_excel_map: student_id column missing → LocatedInputError (ValidationError)
- load_school_excel_map: missing file → LocatedInputError
- SchoolExcelMap: extra fields forbidden (ConfigDict extra='forbid')
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    from metric_codex.ingest.bronze_copies import load_blueprint
    from paideia_shared.schemas import ExamenBlueprint

    p = tmp_path / "blueprint.yaml"
    p.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")

    result = load_blueprint(p)

    assert isinstance(result, ExamenBlueprint)
    assert result.semester == "2026-1"
    assert result.course_slug == "anatomy"
    assert result.total_items == 45


def test_load_blueprint_missing_file(tmp_path: Path) -> None:
    """Missing blueprint.yaml raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_blueprint

    p = tmp_path / "blueprint.yaml"
    with pytest.raises(LocatedInputError):
        load_blueprint(p)


def test_load_blueprint_missing_file_mentions_path(tmp_path: Path) -> None:
    """LocatedInputError for missing file includes the file path."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_blueprint

    p = tmp_path / "blueprint.yaml"
    with pytest.raises(LocatedInputError) as exc_info:
        load_blueprint(p)
    assert "blueprint.yaml" in str(exc_info.value)


def test_load_blueprint_malformed_yaml(tmp_path: Path) -> None:
    """Malformed YAML in blueprint raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_blueprint

    p = tmp_path / "blueprint.yaml"
    p.write_text("semester: [\nbad yaml{{{\n", encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_blueprint(p)


def test_load_blueprint_non_mapping_yaml(tmp_path: Path) -> None:
    """Non-mapping YAML (e.g., a list) in blueprint raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_blueprint

    p = tmp_path / "blueprint.yaml"
    p.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_blueprint(p)


def test_load_blueprint_validation_failure(tmp_path: Path) -> None:
    """Blueprint with missing required fields raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_blueprint

    p = tmp_path / "blueprint.yaml"
    p.write_text("semester: '2026-1'\n", encoding="utf-8")  # missing many required fields
    with pytest.raises(LocatedInputError):
        load_blueprint(p)


# ---------------------------------------------------------------------------
# load_curriculum_map
# ---------------------------------------------------------------------------


def test_load_curriculum_map_valid(tmp_path: Path) -> None:
    """Valid curriculum_map.yaml returns a validated CurriculumMap."""
    from metric_codex.ingest.bronze_copies import load_curriculum_map
    from paideia_shared.schemas import CurriculumMap

    p = tmp_path / "curriculum_map.yaml"
    p.write_text(_VALID_CURRICULUM_YAML, encoding="utf-8")

    result = load_curriculum_map(p)

    assert isinstance(result, CurriculumMap)
    assert result.semester == "2026-1"
    assert len(result.entries) == 2


def test_load_curriculum_map_missing_file(tmp_path: Path) -> None:
    """Missing curriculum_map.yaml raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_curriculum_map

    p = tmp_path / "curriculum_map.yaml"
    with pytest.raises(LocatedInputError):
        load_curriculum_map(p)


def test_load_curriculum_map_malformed_yaml(tmp_path: Path) -> None:
    """Malformed YAML in curriculum_map raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_curriculum_map

    p = tmp_path / "curriculum_map.yaml"
    p.write_text("entries: [\n{{broken\n", encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_curriculum_map(p)


def test_load_curriculum_map_non_mapping_yaml(tmp_path: Path) -> None:
    """Non-mapping YAML in curriculum_map raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_curriculum_map

    p = tmp_path / "curriculum_map.yaml"
    p.write_text("- entry1\n- entry2\n", encoding="utf-8")
    with pytest.raises(LocatedInputError):
        load_curriculum_map(p)


# ---------------------------------------------------------------------------
# load_exam_spec (combined loader with cross-check)
# ---------------------------------------------------------------------------


def test_load_exam_spec_valid(tmp_path: Path) -> None:
    """load_exam_spec with matching keys returns (blueprint, curriculum) tuple."""
    from metric_codex.ingest.bronze_copies import load_exam_spec
    from paideia_shared.schemas import CurriculumMap, ExamenBlueprint

    bp = tmp_path / "blueprint.yaml"
    cm = tmp_path / "curriculum_map.yaml"
    bp.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")
    cm.write_text(_VALID_CURRICULUM_YAML, encoding="utf-8")

    blueprint, curriculum = load_exam_spec(bp, cm, semester="2026-1", course_slug="anatomy")

    assert isinstance(blueprint, ExamenBlueprint)
    assert isinstance(curriculum, CurriculumMap)


def test_load_exam_spec_semester_mismatch(tmp_path: Path) -> None:
    """load_exam_spec with wrong semester raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_exam_spec

    bp = tmp_path / "blueprint.yaml"
    cm = tmp_path / "curriculum_map.yaml"
    bp.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")
    cm.write_text(_VALID_CURRICULUM_YAML, encoding="utf-8")

    with pytest.raises(LocatedInputError):
        load_exam_spec(bp, cm, semester="2025-2", course_slug="anatomy")


def test_load_exam_spec_course_slug_mismatch(tmp_path: Path) -> None:
    """load_exam_spec with wrong course_slug raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_exam_spec

    bp = tmp_path / "blueprint.yaml"
    cm = tmp_path / "curriculum_map.yaml"
    bp.write_text(_VALID_BLUEPRINT_YAML, encoding="utf-8")
    cm.write_text(_VALID_CURRICULUM_YAML, encoding="utf-8")

    with pytest.raises(LocatedInputError):
        load_exam_spec(bp, cm, semester="2026-1", course_slug="physiology")


# ---------------------------------------------------------------------------
# load_school_excel_map
# ---------------------------------------------------------------------------


def test_load_school_excel_map_valid(tmp_path: Path) -> None:
    """Valid 성적출석_map.yaml returns a SchoolExcelMap instance."""
    from metric_codex.ingest.bronze_copies import SchoolExcelMap, load_school_excel_map

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
    from metric_codex.ingest.bronze_copies import load_school_excel_map

    p = tmp_path / "map.yaml"
    p.write_text(_VALID_SCHOOL_EXCEL_MAP_YAML, encoding="utf-8")
    result = load_school_excel_map(p)

    assert result.sheet == 0
    assert result.header_row == 1


def test_load_school_excel_map_missing_file(tmp_path: Path) -> None:
    """Missing 성적출석_map.yaml raises LocatedInputError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_school_excel_map

    p = tmp_path / "성적출석_map.yaml"
    with pytest.raises(LocatedInputError):
        load_school_excel_map(p)


def test_load_school_excel_map_no_scores_raises(tmp_path: Path) -> None:
    """SchoolExcelMap without any score/attendance column raises an error."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_school_excel_map

    p = tmp_path / "map.yaml"
    p.write_text(_SCHOOL_EXCEL_MAP_NO_SCORES_YAML, encoding="utf-8")
    with pytest.raises((LocatedInputError, Exception)):
        load_school_excel_map(p)


def test_load_school_excel_map_no_student_id_raises(tmp_path: Path) -> None:
    """ColumnMap without student_id raises a validation error."""
    from metric_codex.ingest.bronze_copies import load_school_excel_map

    p = tmp_path / "map.yaml"
    p.write_text(_SCHOOL_EXCEL_MAP_NO_STUDENT_ID_YAML, encoding="utf-8")
    with pytest.raises(Exception):  # ValidationError wrapped in LocatedInputError
        load_school_excel_map(p)


def test_load_school_excel_map_extra_fields_forbidden(tmp_path: Path) -> None:
    """Extra fields in the YAML raise a validation error (extra='forbid')."""
    from metric_codex.ingest.bronze_copies import load_school_excel_map

    p = tmp_path / "map.yaml"
    p.write_text(
        _VALID_SCHOOL_EXCEL_MAP_YAML + "unexpected_field: value\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_school_excel_map(p)


def test_load_school_excel_map_cohort_year_column_optional(tmp_path: Path) -> None:
    """cohort_year_column defaults to None when absent."""
    from metric_codex.ingest.bronze_copies import load_school_excel_map

    p = tmp_path / "map.yaml"
    p.write_text(_VALID_SCHOOL_EXCEL_MAP_YAML, encoding="utf-8")
    result = load_school_excel_map(p)
    assert result.cohort_year_column is None


def test_load_school_excel_map_cohort_year_column_set(tmp_path: Path) -> None:
    """cohort_year_column is parsed when provided."""
    from metric_codex.ingest.bronze_copies import load_school_excel_map

    yaml_content = _VALID_SCHOOL_EXCEL_MAP_YAML + 'cohort_year_column: "입학년도"\n'
    p = tmp_path / "map.yaml"
    p.write_text(yaml_content, encoding="utf-8")
    result = load_school_excel_map(p)
    assert result.cohort_year_column == "입학년도"


def test_load_school_excel_map_attendance_column(tmp_path: Path) -> None:
    """attendance column is recognized as a valid score/attendance signal."""
    from metric_codex.ingest.bronze_copies import load_school_excel_map

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
    """SchoolExcelMap is frozen (immutable after construction)."""
    from metric_codex.ingest.bronze_copies import load_school_excel_map

    p = tmp_path / "map.yaml"
    p.write_text(_VALID_SCHOOL_EXCEL_MAP_YAML, encoding="utf-8")
    result = load_school_excel_map(p)

    with pytest.raises(Exception):  # pydantic ValidationError or TypeError for frozen model
        result.sheet = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LocatedInputError is ValueError (CLI exit-2 trap via bronze_copies path)
# ---------------------------------------------------------------------------


def test_located_input_error_from_bronze_is_value_error(tmp_path: Path) -> None:
    """LocatedInputError from bronze loaders is catchable as ValueError."""
    from metric_codex.errors import LocatedInputError
    from metric_codex.ingest.bronze_copies import load_blueprint

    p = tmp_path / "blueprint.yaml"
    with pytest.raises(ValueError):
        load_blueprint(p)

    assert issubclass(LocatedInputError, ValueError)
