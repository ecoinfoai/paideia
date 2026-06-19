"""T029 — Unit tests for read_school_excel and SourceReadResult (RED first).

Tests written before implementation per TDD mandate.

Covers:
- Happy path: 2 students with total/percent/attendance → correct CodexEntry rows
  (right kinds/values/layer/student_id/cohort_year derived from id prefix);
  identities captured.
- Blank score cell for one student → that entry_kind skipped, others present, no error.
- All score cells blank → identity present, zero entries, no error.
- cohort_year_column set → cohort_year read from column, not id prefix.
- Malformed student_id cell → LocatedInputError with row number.
- Non-numeric score cell → LocatedInputError (row + column).
- Configured header missing from sheet → LocatedInputError.
- Determinism: two reads of the same fixture produce equal entries.
- source_record has the right source_id/origin_module/origin_layer/sha256/ingested_at.
- SourceReadResult and compute_sha256 are importable from their modules.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import openpyxl
import pytest
from metric_codex.errors import LocatedInputError
from metric_codex.ingest.bronze_copies import ColumnMap, SchoolExcelMap
from metric_codex.ingest.result import SourceReadResult
from metric_codex.ingest.school_excel import read_school_excel
from metric_codex.output.sha256 import compute_sha256
from paideia_shared.schemas.metric_codex import EntryKind, SourceRecord

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE_SLUG = "anatomy"
_INGESTED_AT = "2026-06-19T00:00:00Z"

# Minimal SchoolExcelMap with score_total + score_percent + attendance all mapped.
_FULL_EXCEL_MAP = SchoolExcelMap(
    semester=_SEMESTER,
    course_slug=_COURSE_SLUG,
    sheet=0,
    header_row=1,
    columns=ColumnMap(
        student_id="학번",
        name_kr="이름",
        score_total="총점",
        score_percent="환산점수",
        attendance="출석",
    ),
)

# Map with only score_total (no percent, no attendance).
_TOTAL_ONLY_MAP = SchoolExcelMap(
    semester=_SEMESTER,
    course_slug=_COURSE_SLUG,
    sheet=0,
    header_row=1,
    columns=ColumnMap(
        student_id="학번",
        name_kr="이름",
        score_total="총점",
    ),
)

# Map with cohort_year_column set.
_COHORT_YEAR_MAP = SchoolExcelMap(
    semester=_SEMESTER,
    course_slug=_COURSE_SLUG,
    sheet=0,
    header_row=1,
    columns=ColumnMap(
        student_id="학번",
        name_kr="이름",
        score_total="총점",
    ),
    cohort_year_column="입학년도",
)


def _make_workbook(tmp_path: Path, rows: list[list]) -> Path:
    """Write a single-sheet workbook with the given row data to tmp_path.

    Args:
        tmp_path: Directory to write the workbook into.
        rows: List of rows; each row is a list of cell values.

    Returns:
        Path to the written xlsx file.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    path = tmp_path / "grades.xlsx"
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# Happy-path: 2 students × (total, percent, attendance)
# ---------------------------------------------------------------------------


def test_happy_path_returns_source_read_result(tmp_path: Path) -> None:
    """read_school_excel returns a SourceReadResult."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
            [2026000002, "테스트B", 70, 75.0, 12],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert isinstance(result, SourceReadResult)


def test_happy_path_entry_count(tmp_path: Path) -> None:
    """Two students × 3 kinds → 6 CodexEntry rows."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
            [2026000002, "테스트B", 70, 75.0, 12],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert len(result.entries) == 6


def test_happy_path_entry_kinds(tmp_path: Path) -> None:
    """All three entry kinds are emitted for each student."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    kinds = {e.entry_kind for e in result.entries}
    assert EntryKind.score_total in kinds
    assert EntryKind.score_percent in kinds
    assert EntryKind.attendance in kinds


def test_happy_path_entry_values(tmp_path: Path) -> None:
    """Numeric values are correctly read as float."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    by_kind = {e.entry_kind: e.value_num for e in result.entries}
    assert by_kind[EntryKind.score_total] == 85.0
    assert by_kind[EntryKind.score_percent] == 90.5
    assert by_kind[EntryKind.attendance] == 15.0


def test_happy_path_layer_minimal(tmp_path: Path) -> None:
    """All entries have layer='minimal'."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert all(e.layer == "minimal" for e in result.entries)


def test_happy_path_student_id_normalized(tmp_path: Path) -> None:
    """student_id is normalized to 10-digit string."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert all(e.student_id == "2026000001" for e in result.entries)


def test_happy_path_cohort_year_from_id_prefix(tmp_path: Path) -> None:
    """cohort_year is derived from first 4 digits of student_id when no column set."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert all(e.cohort_year == 2026 for e in result.entries)


def test_happy_path_semester_set(tmp_path: Path) -> None:
    """semester matches the excel_map.semester."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert all(e.semester == "2026-1" for e in result.entries)


def test_happy_path_source_id_on_entries(tmp_path: Path) -> None:
    """All entries carry source_id = 'school_excel:<filename>'."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    expected_source_id = f"school_excel:{path.name}"
    assert all(e.source_id == expected_source_id for e in result.entries)


def test_happy_path_identities_captured(tmp_path: Path) -> None:
    """identities dict maps student_id → name_kr for all students."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
            [2026000002, "테스트B", 70, 75.0, 12],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert result.identities == {
        "2026000001": "테스트A",
        "2026000002": "테스트B",
    }


def test_happy_path_key_equals_entry_kind_value(tmp_path: Path) -> None:
    """Each entry's key equals its entry_kind value (e.g. 'score_total')."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    for entry in result.entries:
        assert entry.key == entry.entry_kind.value


def test_happy_path_value_text_is_none(tmp_path: Path) -> None:
    """value_text is None for all minimal-layer numeric entries."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert all(e.value_text is None for e in result.entries)


def test_happy_path_domain_and_item_ref_none(tmp_path: Path) -> None:
    """domain and item_ref are None for school-level minimal entries."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert all(e.domain is None for e in result.entries)
    assert all(e.item_ref is None for e in result.entries)


def test_happy_path_observed_at_none(tmp_path: Path) -> None:
    """observed_at is None for school Excel entries (no event date in file)."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert all(e.observed_at is None for e in result.entries)


# ---------------------------------------------------------------------------
# Blank score cell for one kind → that kind skipped, others present
# ---------------------------------------------------------------------------


def test_blank_score_cell_skipped(tmp_path: Path) -> None:
    """A blank score cell does not emit a CodexEntry for that kind."""
    # score_percent is None (blank).
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, None, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    kinds = {e.entry_kind for e in result.entries}
    assert EntryKind.score_percent not in kinds
    assert EntryKind.score_total in kinds
    assert EntryKind.attendance in kinds


def test_blank_score_cell_no_error(tmp_path: Path) -> None:
    """A blank score cell does not raise an error."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, None, 15],
        ],
    )

    # Should not raise.
    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)
    assert len(result.entries) == 2  # only score_total and attendance


# ---------------------------------------------------------------------------
# All score cells blank → identity present, zero entries
# ---------------------------------------------------------------------------


def test_all_scores_blank_no_entries(tmp_path: Path) -> None:
    """Student with all blank score cells contributes no CodexEntry rows."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", None, None, None],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert result.entries == []


def test_all_scores_blank_identity_present(tmp_path: Path) -> None:
    """Student with all blank scores still has their identity recorded."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", None, None, None],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert "2026000001" in result.identities
    assert result.identities["2026000001"] == "테스트A"


# ---------------------------------------------------------------------------
# cohort_year_column set → cohort_year read from column, not id prefix
# ---------------------------------------------------------------------------


def test_cohort_year_from_column(tmp_path: Path) -> None:
    """When cohort_year_column is configured, it overrides id-prefix derivation."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "입학년도"],
            [2026000001, "테스트A", 85, 2024],
        ],
    )

    result = read_school_excel(path, _COHORT_YEAR_MAP, ingested_at=_INGESTED_AT)

    assert all(e.cohort_year == 2024 for e in result.entries)


def test_cohort_year_column_coerced_to_int(tmp_path: Path) -> None:
    """cohort_year column value is coerced to int (may be stored as float in Excel)."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "입학년도"],
            [2026000001, "테스트A", 85, 2024.0],
        ],
    )

    result = read_school_excel(path, _COHORT_YEAR_MAP, ingested_at=_INGESTED_AT)

    assert all(e.cohort_year == 2024 for e in result.entries)


def test_cohort_year_id_prefix_differs_from_column(tmp_path: Path) -> None:
    """When column is set and differs from id prefix, the column wins."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "입학년도"],
            # id prefix is 2026 but column says 2023.
            [2026000001, "테스트A", 85, 2023],
        ],
    )

    result = read_school_excel(path, _COHORT_YEAR_MAP, ingested_at=_INGESTED_AT)

    assert all(e.cohort_year == 2023 for e in result.entries)


# ---------------------------------------------------------------------------
# Error: malformed student_id cell
# ---------------------------------------------------------------------------


def test_malformed_student_id_raises(tmp_path: Path) -> None:
    """Non-digit student_id value raises LocatedInputError."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            ["BADID", "테스트A", 85],
        ],
    )

    with pytest.raises(LocatedInputError):
        read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)


def test_malformed_student_id_error_contains_row(tmp_path: Path) -> None:
    """LocatedInputError for bad student_id includes the data row number."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            ["BADID", "테스트A", 85],
        ],
    )

    with pytest.raises(LocatedInputError) as exc_info:
        read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    # data row 2 (1-based: row 1 = header, row 2 = first data row)
    assert "2" in str(exc_info.value)


def test_malformed_student_id_error_is_value_error(tmp_path: Path) -> None:
    """LocatedInputError is catchable as ValueError (CLI exit-2 contract)."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            ["BADID", "테스트A", 85],
        ],
    )

    with pytest.raises(ValueError):
        read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)


# ---------------------------------------------------------------------------
# Error: non-numeric score cell
# ---------------------------------------------------------------------------


def test_non_numeric_score_raises(tmp_path: Path) -> None:
    """Non-numeric value in score cell raises LocatedInputError."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", "not-a-number"],
        ],
    )

    with pytest.raises(LocatedInputError):
        read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)


def test_non_numeric_score_error_contains_row(tmp_path: Path) -> None:
    """LocatedInputError for bad score includes the row number."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", "not-a-number"],
        ],
    )

    with pytest.raises(LocatedInputError) as exc_info:
        read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    assert "2" in str(exc_info.value)


def test_non_numeric_score_error_contains_column(tmp_path: Path) -> None:
    """LocatedInputError for bad score includes the column header name."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", "not-a-number"],
        ],
    )

    with pytest.raises(LocatedInputError) as exc_info:
        read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    assert "총점" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Error: configured header missing from sheet
# ---------------------------------------------------------------------------


def test_missing_header_raises(tmp_path: Path) -> None:
    """If a configured header column is absent from the sheet, LocatedInputError is raised."""
    # Sheet has no '총점' column but excel_map expects it.
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "WRONG_HEADER"],
            [2026000001, "테스트A", 85],
        ],
    )

    with pytest.raises(LocatedInputError):
        read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)


def test_missing_header_error_mentions_header_name(tmp_path: Path) -> None:
    """LocatedInputError for missing header names the missing header."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "WRONG_HEADER"],
            [2026000001, "테스트A", 85],
        ],
    )

    with pytest.raises(LocatedInputError) as exc_info:
        read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    assert "총점" in str(exc_info.value)


def test_missing_student_id_header_raises(tmp_path: Path) -> None:
    """If student_id column header is absent, LocatedInputError is raised."""
    path = _make_workbook(
        tmp_path,
        [
            ["NO_STUDENT_ID", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    with pytest.raises(LocatedInputError):
        read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)


# ---------------------------------------------------------------------------
# Error: sheet not found
# ---------------------------------------------------------------------------


def test_sheet_by_name_not_found_raises(tmp_path: Path) -> None:
    """Referencing a sheet by name that doesn't exist raises LocatedInputError."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    bad_map = SchoolExcelMap(
        semester=_SEMESTER,
        course_slug=_COURSE_SLUG,
        sheet="NonExistentSheet",
        header_row=1,
        columns=ColumnMap(student_id="학번", score_total="총점"),
    )

    with pytest.raises(LocatedInputError):
        read_school_excel(path, bad_map, ingested_at=_INGESTED_AT)


# ---------------------------------------------------------------------------
# Determinism: two reads produce equal entries
# ---------------------------------------------------------------------------


def test_determinism_equal_entries(tmp_path: Path) -> None:
    """Two reads of the same fixture produce equal entries lists."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
            [2026000002, "테스트B", 70, 75.0, 12],
        ],
    )

    result1 = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)
    result2 = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    assert result1.entries == result2.entries


def test_determinism_stable_sort_order(tmp_path: Path) -> None:
    """Entries are sorted deterministically by (student_id, entry_kind)."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000002, "테스트B", 70, 75.0, 12],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )

    result = read_school_excel(path, _FULL_EXCEL_MAP, ingested_at=_INGESTED_AT)

    # First student_id in sorted order should be 2026000001.
    assert result.entries[0].student_id == "2026000001"


# ---------------------------------------------------------------------------
# source_record correctness
# ---------------------------------------------------------------------------


def test_source_record_type(tmp_path: Path) -> None:
    """source_record is a SourceRecord instance."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    result = read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    assert isinstance(result.source_record, SourceRecord)


def test_source_record_source_id(tmp_path: Path) -> None:
    """source_record.source_id is 'school_excel:<filename>'."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    result = read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    assert result.source_record.source_id == f"school_excel:{path.name}"


def test_source_record_origin_module(tmp_path: Path) -> None:
    """source_record.origin_module == 'school'."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    result = read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    assert result.source_record.origin_module == "school"


def test_source_record_origin_layer(tmp_path: Path) -> None:
    """source_record.origin_layer == 'bronze'."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    result = read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    assert result.source_record.origin_layer == "bronze"


def test_source_record_sha256_length(tmp_path: Path) -> None:
    """source_record.sha256 is a 64-character hex string."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    result = read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    assert len(result.source_record.sha256) == 64
    assert all(c in "0123456789abcdef" for c in result.source_record.sha256)


def test_source_record_sha256_matches_file(tmp_path: Path) -> None:
    """source_record.sha256 matches the SHA-256 of the file bytes."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    result = read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.source_record.sha256 == expected


def test_source_record_ingested_at(tmp_path: Path) -> None:
    """source_record.ingested_at matches the passed ingested_at string."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    result = read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    assert result.source_record.ingested_at == _INGESTED_AT


# ---------------------------------------------------------------------------
# compute_sha256 importable and correct
# ---------------------------------------------------------------------------


def test_compute_sha256_importable() -> None:
    """compute_sha256 is importable from metric_codex.output.sha256."""
    from metric_codex.output.sha256 import compute_sha256  # noqa: F401 (import check)


def test_compute_sha256_correct(tmp_path: Path) -> None:
    """compute_sha256 returns the SHA-256 hex digest of file bytes."""
    p = tmp_path / "test.bin"
    p.write_bytes(b"hello world")

    expected = hashlib.sha256(b"hello world").hexdigest()
    assert compute_sha256(p) == expected


def test_compute_sha256_returns_64_hex_chars(tmp_path: Path) -> None:
    """compute_sha256 always returns exactly 64 lowercase hex chars."""
    p = tmp_path / "file.bin"
    p.write_bytes(b"")

    digest = compute_sha256(p)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


# ---------------------------------------------------------------------------
# SourceReadResult importable and dataclass contract
# ---------------------------------------------------------------------------


def test_source_read_result_importable() -> None:
    """SourceReadResult is importable from metric_codex.ingest.result."""
    from metric_codex.ingest.result import SourceReadResult  # noqa: F401


def test_source_read_result_is_frozen(tmp_path: Path) -> None:
    """SourceReadResult is a frozen dataclass (immutable)."""
    import dataclasses

    assert dataclasses.is_dataclass(SourceReadResult)

    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )

    result = read_school_excel(path, _TOTAL_ONLY_MAP, ingested_at=_INGESTED_AT)

    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        result.entries = []  # type: ignore[misc]
