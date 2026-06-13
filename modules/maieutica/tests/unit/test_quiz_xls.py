"""T032 — Unit tests: LMS quiz `.xls` writer determinism + guide sheet.

Covers:
- Byte-determinism (SC-009 / R1): two writes are byte-identical, enforced by
  ``maieutica.output.determinism.gate_xls_deterministic``.
- The frozen guide asset loads with the immutable sheet name.
- Headers come from ``templates/quiz_column_map.yaml`` (Constitution III), not
  hardcoded in the writer.
"""

from __future__ import annotations

from pathlib import Path

import xlrd
from maieutica.output.determinism import gate_xls_deterministic
from maieutica.output.quiz_xls import (
    QUIZ_HEADERS,
    guide_sheet_name,
    write_quiz_xls,
)
from paideia_shared.schemas import QuizItemCandidate
from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation


def _candidate(item_no: int, answer_no: int, week: int = 9) -> QuizItemCandidate:
    options = [f"보기 {item_no}-{i} 길이 충분한 보기 문자열 example" for i in range(1, 6)]
    wrong = "오답 설명."
    leap_text = "도약 설명."
    return QuizItemCandidate(
        semester="2026-1",
        course_slug="anatomy",
        item_no=item_no,
        week=week,
        chapter_no=8,
        chapter="호흡계통",
        question_type="지식축적",
        difficulty="중",
        stem_polarity="부정형",
        text=f"{item_no}번 문제",
        options=options,
        answer_no=answer_no,
        option_evidence=[f"근거{i}" for i in range(1, 6)],
        wrong_explanation=wrong,
        leap=LeapExplanation(text=leap_text),
        answer_explanation_combined=f"{wrong} ─ 도약 ─ {leap_text}",
        option_length_ok=True,
        explanation_length_ok=True,
    )


def _sample() -> list[QuizItemCandidate]:
    return [
        _candidate(item_no=1, answer_no=3),
        _candidate(item_no=2, answer_no=1),
    ]


def test_guide_sheet_name_is_lms_contract() -> None:
    """The frozen guide sheet name is the immutable LMS instruction-sheet name."""
    assert guide_sheet_name() == "필독! - 반드시 확인해 주세요!"


def test_headers_count_and_order() -> None:
    """11 headers driven from the column map, fixed order."""
    assert len(QUIZ_HEADERS) == 11
    assert QUIZ_HEADERS[0] == "문제번호"
    assert QUIZ_HEADERS[-1] == "문항유형"


def test_quiz_xls_is_byte_deterministic(tmp_path: Path) -> None:
    """SC-009/R1: writing the same candidates twice yields byte-identical `.xls`."""
    candidates = _sample()

    def writer(path: Path) -> None:
        write_quiz_xls(path, candidates, week=9)

    # Raises AssertionError if the two writes differ.
    gate_xls_deterministic(writer, work_dir=tmp_path)


def test_guide_sheet_written_with_frozen_cells(tmp_path: Path) -> None:
    """Sheet 0 carries the frozen guide title cell, proving the asset is written."""
    out = tmp_path / "QuestionUploadExcel_9주차.xls"
    write_quiz_xls(out, _sample(), week=9)
    book = xlrd.open_workbook(str(out))
    sheet0 = book.sheet_by_index(0)
    assert sheet0.name == guide_sheet_name()
    # The real guide has '문제등록 안내문' at (2, 1).
    assert sheet0.cell(2, 1).value == "문제등록 안내문"
    assert sheet0.cell(2, 1).ctype == xlrd.XL_CELL_TEXT


def test_week_zero_padding_three_digits(tmp_path: Path) -> None:
    """예상주차 zero-pads to 3 digits as text (week 1 → '001')."""
    out = tmp_path / "QuestionUploadExcel_1주차.xls"
    write_quiz_xls(out, [_candidate(item_no=1, answer_no=2, week=1)], week=1)
    book = xlrd.open_workbook(str(out))
    sheet1 = book.sheet_by_index(1)
    col = {h: i for i, h in enumerate(QUIZ_HEADERS)}
    cell = sheet1.cell(1, col["예상주차"])
    assert cell.ctype == xlrd.XL_CELL_TEXT
    assert cell.value == "001"


def test_quiz_xls_empty_candidates(tmp_path: Path) -> None:
    """Empty candidate list → header-only Sheet1, still valid + byte-deterministic."""
    out = tmp_path / "QuestionUploadExcel_9주차.xls"
    write_quiz_xls(out, [], week=9)

    book = xlrd.open_workbook(str(out))
    assert book.nsheets == 2
    sheet0 = book.sheet_by_index(0)
    assert sheet0.name == guide_sheet_name()
    sheet1 = book.sheet_by_index(1)
    assert sheet1.name == "Sheet1"
    # Header row only — no data rows.
    assert sheet1.nrows == 1
    assert [sheet1.cell(0, c).value for c in range(sheet1.ncols)] == list(QUIZ_HEADERS)

    # Still byte-deterministic with an empty list.
    def writer(path: Path) -> None:
        write_quiz_xls(path, [], week=9)

    gate_xls_deterministic(writer, work_dir=tmp_path)
