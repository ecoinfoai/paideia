"""T029 / U1b-1 hardening — Unit tests for read_school_excel and SourceReadResult.

Tests written before implementation per TDD mandate.

Covers:
- Happy path: students with total/percent/attendance → correct CodexEntry rows
  (kinds/values/layer/student_id/cohort_year/key/source_id; identities captured).
- Blank score cell → that entry_kind skipped; all-blank → identity only, no error.
- cohort_year_column set → cohort_year read from column (coerced, validated).
- Boundary errors (all LocatedInputError): malformed student_id, non-numeric
  score, boolean score, missing/duplicate header, empty sheet, header_row past
  the data, missing/out-of-range sheet, student_id=None with a present score,
  non-numeric / out-of-range cohort_year.
- Determinism: two reads produce equal entries; stable sort order.
- source_record: source_id/origin_module/origin_layer/sha256/ingested_at, and
  caller-supplied source_path used verbatim.
- SourceReadResult / compute_sha256 importable and correct.
"""

from __future__ import annotations

import dataclasses
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
# Fixtures / builders
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE_SLUG = "anatomy"
_INGESTED_AT = "2026-06-19T00:00:00Z"
_SOURCE_PATH = "data/bronze/metric-codex/2026-1-anatomy/성적출석.xlsx"

# Map with score_total + score_percent + attendance all mapped.
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


def _make_workbook(tmp_path: Path, rows: list[list], *, name: str = "grades.xlsx") -> Path:
    """Write a single-sheet workbook with the given row data to tmp_path.

    Args:
        tmp_path: Directory to write the workbook into.
        rows: List of rows; each row is a list of cell values.
        name: Output file name.

    Returns:
        Path to the written xlsx file.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    path = tmp_path / name
    wb.save(path)
    return path


def _read(path: Path, excel_map: SchoolExcelMap = _TOTAL_ONLY_MAP) -> SourceReadResult:
    """Call read_school_excel with the standard test ingested_at / source_path."""
    return read_school_excel(
        path,
        excel_map,
        ingested_at=_INGESTED_AT,
        source_path=_SOURCE_PATH,
    )


@pytest.fixture
def one_student_result(tmp_path: Path) -> SourceReadResult:
    """A SourceReadResult for one student with total/percent/attendance present."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )
    return _read(path, _FULL_EXCEL_MAP)


# ---------------------------------------------------------------------------
# Happy path — one student, all fields asserted on the shared fixture
# ---------------------------------------------------------------------------


def test_happy_path_returns_source_read_result(one_student_result: SourceReadResult) -> None:
    """read_school_excel returns a frozen SourceReadResult."""
    assert isinstance(one_student_result, SourceReadResult)
    assert dataclasses.is_dataclass(SourceReadResult)


def test_happy_path_entries(one_student_result: SourceReadResult) -> None:
    """One student × 3 kinds → 3 correct minimal-layer CodexEntry rows."""
    entries = one_student_result.entries
    assert len(entries) == 3

    by_kind = {e.entry_kind: e for e in entries}
    assert set(by_kind) == {
        EntryKind.score_total,
        EntryKind.score_percent,
        EntryKind.attendance,
    }
    assert by_kind[EntryKind.score_total].value_num == 85.0
    assert by_kind[EntryKind.score_percent].value_num == 90.5
    assert by_kind[EntryKind.attendance].value_num == 15.0

    for entry in entries:
        assert entry.layer == "minimal"
        assert entry.student_id == "2026000001"
        assert entry.cohort_year == 2026  # derived from id prefix
        assert entry.semester == "2026-1"
        assert entry.source_id == "school_excel:grades.xlsx"
        assert entry.key == entry.entry_kind.value
        assert entry.value_text is None
        assert entry.domain is None
        assert entry.item_ref is None
        assert entry.observed_at is None


def test_happy_path_identities(one_student_result: SourceReadResult) -> None:
    """identities maps student_id → name_kr."""
    assert one_student_result.identities == {"2026000001": "테스트A"}


def test_happy_path_two_students_identities(tmp_path: Path) -> None:
    """Two students → 6 entries and both identities captured."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, 90.5, 15],
            [2026000002, "테스트B", 70, 75.0, 12],
        ],
    )
    result = _read(path, _FULL_EXCEL_MAP)

    assert len(result.entries) == 6
    assert result.identities == {
        "2026000001": "테스트A",
        "2026000002": "테스트B",
    }


# ---------------------------------------------------------------------------
# Blank cells
# ---------------------------------------------------------------------------


def test_blank_score_cell_skipped(tmp_path: Path) -> None:
    """A blank score cell skips that kind (no error); other kinds still emitted."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", 85, None, 15],
        ],
    )
    result = _read(path, _FULL_EXCEL_MAP)

    kinds = {e.entry_kind for e in result.entries}
    assert kinds == {EntryKind.score_total, EntryKind.attendance}


def test_all_scores_blank_identity_only(tmp_path: Path) -> None:
    """All-blank score cells → identity present, zero entries, no error."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000001, "테스트A", None, None, None],
        ],
    )
    result = _read(path, _FULL_EXCEL_MAP)

    assert result.entries == []
    assert result.identities == {"2026000001": "테스트A"}


# ---------------------------------------------------------------------------
# cohort_year_column
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw_year, expected", [(2024, 2024), (2024.0, 2024), (2023, 2023)])
def test_cohort_year_from_column(tmp_path: Path, raw_year: object, expected: int) -> None:
    """cohort_year_column overrides id-prefix derivation; coerced to int."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "입학년도"],
            [2026000001, "테스트A", 85, raw_year],
        ],
    )
    result = _read(path, _COHORT_YEAR_MAP)

    assert all(e.cohort_year == expected for e in result.entries)


def test_cohort_year_column_non_numeric_raises(tmp_path: Path) -> None:
    """Non-numeric cohort_year value raises LocatedInputError (row + column)."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "입학년도"],
            [2026000001, "테스트A", 85, "졸업"],
        ],
    )
    with pytest.raises(LocatedInputError) as exc_info:
        _read(path, _COHORT_YEAR_MAP)
    assert "입학년도" in str(exc_info.value)
    assert "2" in str(exc_info.value)


def test_cohort_year_column_out_of_range_raises(tmp_path: Path) -> None:
    """cohort_year outside [2000, 2100] raises LocatedInputError."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "입학년도"],
            [2026000001, "테스트A", 85, 1999],
        ],
    )
    with pytest.raises(LocatedInputError):
        _read(path, _COHORT_YEAR_MAP)


# ---------------------------------------------------------------------------
# Boundary errors — student_id
# ---------------------------------------------------------------------------


def test_malformed_student_id_raises_with_row(tmp_path: Path) -> None:
    """Non-digit student_id raises LocatedInputError naming the data row."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            ["BADID", "테스트A", 85],
        ],
    )
    with pytest.raises(LocatedInputError) as exc_info:
        _read(path)
    assert "2" in str(exc_info.value)
    # LocatedInputError subclasses ValueError (CLI exit-2 trap).
    assert isinstance(exc_info.value, ValueError)


def test_none_student_id_with_score_raises(tmp_path: Path) -> None:
    """student_id=None with a present score → LocatedInputError (no silent skip)."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [None, "테스트A", 85],
        ],
    )
    with pytest.raises(LocatedInputError):
        _read(path)


# ---------------------------------------------------------------------------
# Boundary errors — score cells
# ---------------------------------------------------------------------------


def test_non_numeric_score_raises_with_row_and_column(tmp_path: Path) -> None:
    """Non-numeric score raises LocatedInputError naming row and column."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", "not-a-number"],
        ],
    )
    with pytest.raises(LocatedInputError) as exc_info:
        _read(path)
    msg = str(exc_info.value)
    assert "2" in msg
    assert "총점" in msg


def test_boolean_score_raises(tmp_path: Path) -> None:
    """A boolean score cell raises LocatedInputError (not coerced to 1.0/0.0)."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", True],
        ],
    )
    with pytest.raises(LocatedInputError) as exc_info:
        _read(path)
    assert "총점" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Boundary errors — headers
# ---------------------------------------------------------------------------


def test_missing_score_header_names_header(tmp_path: Path) -> None:
    """A configured header absent from the sheet raises LocatedInputError naming it."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "WRONG_HEADER"],
            [2026000001, "테스트A", 85],
        ],
    )
    with pytest.raises(LocatedInputError) as exc_info:
        _read(path)
    assert "총점" in str(exc_info.value)


def test_missing_student_id_header_raises(tmp_path: Path) -> None:
    """Absent student_id header raises LocatedInputError."""
    path = _make_workbook(
        tmp_path,
        [
            ["NO_STUDENT_ID", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )
    with pytest.raises(LocatedInputError):
        _read(path)


def test_duplicate_header_raises(tmp_path: Path) -> None:
    """Duplicate column headers raise LocatedInputError (no silent overwrite)."""
    # '총점' appears twice — last-wins would lose the first column's data.
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "총점"],
            [2026000001, "테스트A", 85, 99],
        ],
    )
    with pytest.raises(LocatedInputError) as exc_info:
        _read(path)
    assert "총점" in str(exc_info.value)
    assert "duplicate" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Boundary errors — empty / short sheets
# ---------------------------------------------------------------------------


def test_empty_sheet_raises(tmp_path: Path) -> None:
    """An empty sheet (no rows) raises LocatedInputError, not bare StopIteration."""
    wb = openpyxl.Workbook()
    path = tmp_path / "empty.xlsx"
    wb.save(path)

    with pytest.raises(LocatedInputError):
        _read(path)


def test_header_row_past_data_raises(tmp_path: Path) -> None:
    """header_row beyond the populated range raises LocatedInputError."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )
    # header_row=10 is far past the 2 populated rows.
    far_map = SchoolExcelMap(
        semester=_SEMESTER,
        course_slug=_COURSE_SLUG,
        sheet=0,
        header_row=10,
        columns=ColumnMap(student_id="학번", score_total="총점"),
    )
    with pytest.raises(LocatedInputError):
        read_school_excel(path, far_map, ingested_at=_INGESTED_AT, source_path=_SOURCE_PATH)


# ---------------------------------------------------------------------------
# Boundary errors — sheet selection
# ---------------------------------------------------------------------------


def test_sheet_by_name_not_found_raises(tmp_path: Path) -> None:
    """A sheet name that does not exist raises LocatedInputError."""
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
        read_school_excel(path, bad_map, ingested_at=_INGESTED_AT, source_path=_SOURCE_PATH)


def test_sheet_index_out_of_range_raises(tmp_path: Path) -> None:
    """A sheet index beyond the workbook's sheet count raises LocatedInputError."""
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
        sheet=5,  # workbook has only 1 sheet
        header_row=1,
        columns=ColumnMap(student_id="학번", score_total="총점"),
    )
    with pytest.raises(LocatedInputError):
        read_school_excel(path, bad_map, ingested_at=_INGESTED_AT, source_path=_SOURCE_PATH)


# ---------------------------------------------------------------------------
# Determinism
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
    assert _read(path, _FULL_EXCEL_MAP).entries == _read(path, _FULL_EXCEL_MAP).entries


def test_determinism_stable_sort_order(tmp_path: Path) -> None:
    """Entries are sorted by (student_id, entry_kind, key) regardless of row order."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000002, "테스트B", 70, 75.0, 12],
            [2026000001, "테스트A", 85, 90.5, 15],
        ],
    )
    result = _read(path, _FULL_EXCEL_MAP)
    assert result.entries[0].student_id == "2026000001"


# ---------------------------------------------------------------------------
# source_record
# ---------------------------------------------------------------------------


def test_source_record_fields(one_student_result: SourceReadResult) -> None:
    """source_record carries the right provenance fields."""
    rec = one_student_result.source_record
    assert isinstance(rec, SourceRecord)
    assert rec.source_id == "school_excel:grades.xlsx"
    assert rec.origin_module == "school"
    assert rec.origin_layer == "bronze"
    assert rec.ingested_at == _INGESTED_AT
    assert len(rec.sha256) == 64
    assert all(c in "0123456789abcdef" for c in rec.sha256)


def test_source_path_used_verbatim(tmp_path: Path) -> None:
    """source_record.source_path is the caller-supplied string, unmodified."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )
    result = read_school_excel(
        path,
        _TOTAL_ONLY_MAP,
        ingested_at=_INGESTED_AT,
        source_path="data/bronze/metric-codex/2026-1-anatomy/성적출석.xlsx",
    )
    assert (
        result.source_record.source_path
        == "data/bronze/metric-codex/2026-1-anatomy/성적출석.xlsx"
    )


def test_source_record_sha256_matches_file(tmp_path: Path) -> None:
    """source_record.sha256 matches the SHA-256 of the file bytes."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
        ],
    )
    result = _read(path)
    assert result.source_record.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# compute_sha256 + SourceReadResult helpers
# ---------------------------------------------------------------------------


def test_compute_sha256_correct(tmp_path: Path) -> None:
    """compute_sha256 returns the 64-hex SHA-256 digest of file bytes."""
    p = tmp_path / "test.bin"
    p.write_bytes(b"hello world")
    digest = compute_sha256(p)
    assert digest == hashlib.sha256(b"hello world").hexdigest()
    assert len(digest) == 64


def test_source_read_result_is_frozen(one_student_result: SourceReadResult) -> None:
    """SourceReadResult is immutable."""
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        one_student_result.entries = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# T025 — duplicate student_id → located LocatedInputError naming the second row
# ---------------------------------------------------------------------------


def test_duplicate_student_id_raises_located_on_second_row(tmp_path: Path) -> None:
    """Two rows with the same student_id and conflicting totals → LocatedInputError.

    RED: before T030 fix, the second row silently overwrites the first in
    ``identities`` and appends a second score entry — last-write-wins.  The fix
    must raise immediately on the duplicate id naming the second row number.
    """
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점"],
            [2026000001, "테스트A", 85],
            [2026000001, "테스트A다른이름", 99],  # same id, conflicting total
        ],
    )
    with pytest.raises(LocatedInputError) as exc_info:
        _read(path)

    msg = str(exc_info.value)
    # Must name the second row (row 3, 1-based, in the sheet).
    assert "3" in msg, f"expected row 3 in error; got: {msg!r}"
    # Must include the duplicate student_id value.
    assert "2026000001" in msg, f"expected student_id in error; got: {msg!r}"


def test_duplicate_student_id_raises_for_full_map(tmp_path: Path) -> None:
    """Duplicate id raises even when all three score columns are mapped (FULL_MAP)."""
    path = _make_workbook(
        tmp_path,
        [
            ["학번", "이름", "총점", "환산점수", "출석"],
            [2026000002, "홍길동", 70, 75.0, 12],
            [2026000002, "홍길동복사", 80, 85.0, 14],  # duplicate
        ],
    )
    with pytest.raises(LocatedInputError) as exc_info:
        _read(path, _FULL_EXCEL_MAP)

    msg = str(exc_info.value)
    assert "2026000002" in msg
