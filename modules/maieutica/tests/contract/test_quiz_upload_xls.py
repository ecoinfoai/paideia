"""T024 — Contract test: LMS quiz upload `.xls` (SC-003 roundtrip).

Writes a `.xls` from sample :class:`QuizItemCandidate` objects via
:func:`maieutica.output.quiz_xls.write_quiz_xls`, reads it back with xlrd, and
asserts the immutable LMS contract (``contracts/quiz_upload_xls.md``):

- Sheet 0 name == the frozen guide-sheet name.
- Sheet 1 named ``'Sheet1'`` with 11 headers in exact order.
- N data rows mirroring the candidates.
- Per-column ``cell.ctype``: ``문제번호`` is XL_CELL_NUMBER; ``답안``,
  ``예상주차`` (``"009"``), ``문항유형`` (``"002"``) are XL_CELL_TEXT with
  zero-padding preserved.
"""

from __future__ import annotations

from pathlib import Path

import xlrd
from maieutica.output.quiz_xls import (
    QUIZ_HEADERS,
    guide_sheet_name,
    write_quiz_xls,
)
from paideia_shared.schemas import QuizItemCandidate
from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation


def _candidate(
    item_no: int,
    answer_no: int,
    week: int = 9,
) -> QuizItemCandidate:
    options = [f"보기 {item_no}-{i} 정도 길이의 보기 문자열입니다 abcdef" for i in range(1, 6)]
    wrong = "오답에 대한 설명입니다."
    leap_text = "도약 설명 본문입니다."
    combined = f"{wrong} ─ 도약 ─ {leap_text}"
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
        text=f"{item_no}번 문제: 가장 옳지 않은 것을 고르세요.",
        options=options,
        answer_no=answer_no,
        option_evidence=[f"근거{i}" for i in range(1, 6)],
        wrong_explanation=wrong,
        leap=LeapExplanation(text=leap_text),
        answer_explanation_combined=combined,
        option_length_ok=True,
        explanation_length_ok=True,
    )


def test_quiz_xls_roundtrip_structure_and_cell_types(tmp_path: Path) -> None:
    """SC-003: write → xlrd read-back → assert sheets, headers, cell types."""
    candidates = [
        _candidate(item_no=1, answer_no=3, week=9),
        _candidate(item_no=2, answer_no=2, week=9),
        _candidate(item_no=3, answer_no=5, week=9),
    ]
    out = tmp_path / "QuestionUploadExcel_9주차.xls"
    write_quiz_xls(out, candidates, week=9)

    book = xlrd.open_workbook(str(out))
    assert book.nsheets == 2

    # Sheet 0: frozen guide sheet (name is the immutable LMS contract).
    sheet0 = book.sheet_by_index(0)
    assert sheet0.name == guide_sheet_name()

    # Sheet 1: data sheet.
    sheet1 = book.sheet_by_index(1)
    assert sheet1.name == "Sheet1"

    # Header row: 11 headers in exact order.
    header_values = [sheet1.cell(0, c).value for c in range(sheet1.ncols)]
    assert header_values == list(QUIZ_HEADERS)
    assert len(QUIZ_HEADERS) == 11

    # N data rows.
    assert sheet1.nrows == 1 + len(candidates)

    col = {h: i for i, h in enumerate(QUIZ_HEADERS)}

    # Row 1 maps candidate 1 (answer_no=3, week=9).
    r = 1
    # 문제번호 → NUMBER, value 1.
    cell_num = sheet1.cell(r, col["문제번호"])
    assert cell_num.ctype == xlrd.XL_CELL_NUMBER
    assert cell_num.value == 1

    # 답안 → TEXT "3" (SC-003 trap: text even without leading zero).
    cell_ans = sheet1.cell(r, col["답안"])
    assert cell_ans.ctype == xlrd.XL_CELL_TEXT
    assert cell_ans.value == "3"

    # 예상주차 → TEXT "009" (zero-padded preserved).
    cell_week = sheet1.cell(r, col["예상주차"])
    assert cell_week.ctype == xlrd.XL_CELL_TEXT
    assert cell_week.value == "009"

    # 문항유형 → TEXT "002" constant (zero-padded preserved).
    cell_type = sheet1.cell(r, col["문항유형"])
    assert cell_type.ctype == xlrd.XL_CELL_TEXT
    assert cell_type.value == "002"

    # 문제내용 / 보기1..5 / 답안설명 → TEXT.
    for name in ("문제내용", "보기1", "보기2", "보기3", "보기4", "보기5", "답안설명"):
        assert sheet1.cell(r, col[name]).ctype == xlrd.XL_CELL_TEXT

    # All data rows: 문제번호 numeric, 답안 text.
    for i, cand in enumerate(candidates):
        rr = i + 1
        assert sheet1.cell(rr, col["문제번호"]).ctype == xlrd.XL_CELL_NUMBER
        assert sheet1.cell(rr, col["문제번호"]).value == cand.item_no
        assert sheet1.cell(rr, col["답안"]).ctype == xlrd.XL_CELL_TEXT
        assert sheet1.cell(rr, col["답안"]).value == str(cand.answer_no)
        assert sheet1.cell(rr, col["예상주차"]).value == "009"
        assert sheet1.cell(rr, col["문항유형"]).value == "002"
