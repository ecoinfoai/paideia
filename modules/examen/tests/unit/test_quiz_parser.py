"""T040 — Unit: quiz parser load_quiz_inventory (synthetic in-memory rows).

TDD (RED phase): tests written before implementation.

Tests the row→SourceInventoryEntry mapping function using synthetic
in-memory row dicts — isolated from xlrd file I/O.
The file-read path is covered by T039 devShell manual column dump.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from paideia_shared.schemas import CurriculumEntry, CurriculumMap, SourceInventoryEntry

_SEMESTER = "2026-1"
_COURSE = "anatomy"


def _curriculum() -> CurriculumMap:
    return CurriculumMap(
        semester=_SEMESTER,
        course_slug=_COURSE,
        entries=[
            CurriculumEntry(week=9, chapter="9장 호흡계통", chapter_no=9, subtopic=None, sections=[]),
            CurriculumEntry(week=10, chapter="10장 근육계통", chapter_no=10, subtopic=None, sections=[]),
            CurriculumEntry(week=11, chapter="11장 소화계통", chapter_no=11, subtopic=None, sections=[]),
        ],
    )


def _quiz_row(  # noqa: N803
    *,
    번호: float = 1.0,  # noqa: N803
    문제내용: str = "호흡에 대한 설명으로 옳지 않은 것은?",  # noqa: N803
    예상주차: str = "009",  # noqa: N803
    보기1: str = "보기A",  # noqa: N803
    보기2: str = "보기B",  # noqa: N803
    보기3: str = "보기C",  # noqa: N803
    보기4: str = "보기D",  # noqa: N803
    보기5: str = "보기E",  # noqa: N803
    답안: str = "3",  # noqa: N803
    답안설명: str = "설명 텍스트",  # noqa: N803
    문항유형: str = "002",  # noqa: N803
) -> dict[str, object]:
    """Build a synthetic quiz row dict matching real .xls column structure."""
    return {
        "문제번호": 번호,
        "문제내용": 문제내용,
        "예상주차": 예상주차,
        "보기1": 보기1,
        "보기2": 보기2,
        "보기3": 보기3,
        "보기4": 보기4,
        "보기5": 보기5,
        "답안": 답안,
        "답안설명": 답안설명,
        "문항유형": 문항유형,
    }


# ---------------------------------------------------------------------------
# Tests: rows_to_entries (pure mapping function)
# ---------------------------------------------------------------------------


class TestRowsToEntries:
    """Unit tests for the row→SourceInventoryEntry mapping logic."""

    def test_basic_row_maps_to_entry(self) -> None:
        """A well-formed row maps to a SourceInventoryEntry with all fields set."""
        from examen.ingest.source_inventory import rows_to_entries

        rows = [_quiz_row()]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        assert len(entries) == 1
        e = entries[0]
        assert isinstance(e, SourceInventoryEntry)
        assert e.source == "quiz"
        assert e.semester == _SEMESTER
        assert e.course_slug == _COURSE

    def test_stem_populated_from_문제내용(self) -> None:  # noqa: N802
        """e.stem == row['문제내용']."""
        from examen.ingest.source_inventory import rows_to_entries

        rows = [_quiz_row(문제내용="특수 발문 텍스트")]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        assert entries[0].stem == "특수 발문 텍스트"

    def test_options_populated_from_보기(self) -> None:  # noqa: N802
        """e.options has 5 items matching 보기1..보기5."""
        from examen.ingest.source_inventory import rows_to_entries

        rows = [_quiz_row(보기1="A", 보기2="B", 보기3="C", 보기4="D", 보기5="E")]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        e = entries[0]
        assert e.options == ["A", "B", "C", "D", "E"]

    def test_answer_populated_from_답안(self) -> None:  # noqa: N802
        """e.answer == row['답안'] (string)."""
        from examen.ingest.source_inventory import rows_to_entries

        rows = [_quiz_row(답안="4")]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        assert entries[0].answer == "4"

    def test_chapter_no_resolved_via_curriculum_map(self) -> None:
        """chapter_no is resolved from week via curriculum_map."""
        from examen.ingest.source_inventory import rows_to_entries

        rows = [_quiz_row()]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        assert entries[0].chapter_no == 9  # week 9 → chapter 9

    def test_week_set_correctly(self) -> None:
        """e.week == the week argument passed to rows_to_entries."""
        from examen.ingest.source_inventory import rows_to_entries

        rows = [_quiz_row()]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=10, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        assert entries[0].week == 10

    def test_source_ref_format(self) -> None:
        """source_ref has format '퀴즈:{week}주#{row_number}' (fallback positional)."""
        from examen.ingest.source_inventory import rows_to_entries

        rows = [_quiz_row(번호=1.0), _quiz_row(번호=2.0)]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        assert entries[0].source_ref == "퀴즈:9주#1"
        assert entries[1].source_ref == "퀴즈:9주#2"

    def test_source_ref_uses_physical_sheet_row(self) -> None:
        """When '_sheet_row' is present, source_ref uses the physical sheet row number."""
        from examen.ingest.source_inventory import rows_to_entries

        # Two rows whose physical sheet rows are 2 and 5 (a blank row at 3-4 was skipped)
        rows = [
            {**_quiz_row(번호=1.0), "_sheet_row": 2},
            {**_quiz_row(번호=2.0), "_sheet_row": 5},
        ]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        assert entries[0].source_ref == "퀴즈:9주#2"
        assert entries[1].source_ref == "퀴즈:9주#5"

    def test_blank_mid_sheet_row_does_not_shift_source_ref(self) -> None:
        """A blank mid-sheet row keeps later items anchored to their real .xls row.

        Reproduces load_quiz_inventory's row-building logic: header at sheet row 1,
        data at sheet rows 2 and 3, a BLANK row at sheet row 4, then data at sheet
        row 5.  After blank-row filtering, the surviving items must carry physical
        rows 2, 3, 5 — NOT renumbered 1, 2, 3 (which would point a professor to the
        wrong physical row).  Constitution V: 감사 추적성.
        """
        from examen.ingest.source_inventory import rows_to_entries

        # Simulate xlrd reading sheet rows 1..5 (row 0 = header, skipped upstream).
        # row 4 (physical) is blank → skipped; physical row counter still advances.
        sheet_rows = [
            ("Q1 발문", "2"),   # physical row 2
            ("Q2 발문", "3"),   # physical row 3
            ("", ""),          # physical row 4 — blank, skipped
            ("Q3 발문", "5"),   # physical row 5
        ]
        rows: list[dict[str, object]] = []
        for offset, (stem, _physical) in enumerate(sheet_rows):
            physical_row = offset + 2  # header is physical row 1, data starts at 2
            if not str(stem).strip():
                continue  # blank row skipped, physical_row advances
            row = _quiz_row(문제내용=stem)
            row["_sheet_row"] = physical_row
            rows.append(row)

        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        assert len(entries) == 3
        refs = [e.source_ref for e in entries]
        # The third surviving item must be anchored to physical row 5 (not #3)
        assert refs == ["퀴즈:9주#2", "퀴즈:9주#3", "퀴즈:9주#5"], (
            f"blank-row filtering shifted source_ref off the physical row: {refs}"
        )

    def test_multiple_rows_produces_multiple_entries(self) -> None:
        """Multiple rows → multiple SourceInventoryEntry objects."""
        from examen.ingest.source_inventory import rows_to_entries

        rows = [_quiz_row(번호=float(i)) for i in range(1, 6)]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        assert len(entries) == 5

    def test_unknown_week_raises(self) -> None:
        """rows_to_entries raises ValueError if week not in curriculum_map."""
        from examen.ingest.source_inventory import rows_to_entries

        rows = [_quiz_row()]
        cm = _curriculum()
        with pytest.raises(ValueError, match="curriculum_map"):
            rows_to_entries(rows, week=99, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)

    def test_numeric_답안_coerced_to_str(self) -> None:  # noqa: N802
        """Numeric 답안 value (3.0 float from xlrd) is coerced to exact str '3'."""
        from examen.ingest.source_inventory import rows_to_entries

        # xlrd returns numeric cells as float (e.g. 3.0); exercise the float→str path
        rows = [_quiz_row(답안=3.0)]  # type: ignore[arg-type]
        cm = _curriculum()
        entries = rows_to_entries(rows, week=9, curriculum_map=cm, semester=_SEMESTER, course_slug=_COURSE)
        # float 3.0 must coerce to the exact string "3" (not "3.0")
        assert isinstance(entries[0].answer, str)
        assert entries[0].answer == "3"


# ---------------------------------------------------------------------------
# Tests: quiz_column_map.yaml exists and has expected shape
# ---------------------------------------------------------------------------


class TestQuizColumnMap:
    """quiz_column_map.yaml exists and maps required fields."""

    def test_column_map_yaml_exists(self) -> None:
        """modules/examen/templates/quiz_column_map.yaml exists."""
        here = Path(__file__).parent.parent.parent  # modules/examen
        col_map = here / "templates" / "quiz_column_map.yaml"
        assert col_map.exists(), f"quiz_column_map.yaml not found at {col_map}"

    def test_column_map_has_required_keys(self) -> None:
        """quiz_column_map.yaml has keys: stem, options, answer, sheet."""
        import yaml

        here = Path(__file__).parent.parent.parent
        col_map = here / "templates" / "quiz_column_map.yaml"
        if not col_map.exists():
            pytest.skip("quiz_column_map.yaml not yet created")
        data = yaml.safe_load(col_map.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "quiz_column_map.yaml must be a mapping"
        assert "stem" in data, "quiz_column_map.yaml missing 'stem' key"
        assert "options" in data, "quiz_column_map.yaml missing 'options' key"
        assert "answer" in data, "quiz_column_map.yaml missing 'answer' key"
        assert "sheet" in data, "quiz_column_map.yaml missing 'sheet' key"
