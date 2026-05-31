"""T029-a — xlsx writer: flatten ExamItemDraft list to 28-column sheet.

``write_xlsx(items, path)`` produces a single-sheet xlsx with the exact
28-column layout defined in
``specs/008-examen-question-gen/contracts/exam_draft_outputs.md``.

Column order (28 columns):
  1  번호           — item_no
  2  출처           — source (교과서 / 형성평가 / 퀴즈)
  3  원본출처식별자  — source_ref (교과서는 공백)
  4  챕터           — chapter
  5  절             — section
  6  주차           — week
  7  핵심개념        — key_concept
  8  강조여부        — is_emphasized → 강의강조 / 자습 / ""
  9  문제유형        — question_type
  10 난이도          — difficulty
  11 문두방향        — stem_polarity
  12 문제            — text
  13 보기1           — options[0]
  14 보기2           — options[1]
  15 보기3           — options[2]
  16 보기4           — options[3]
  17 보기5           — options[4]
  18 정답            — answer_no
  19 보기별오답근거  — distractor_rationale joined by "\\n"
  20 오답설명        — wrong_explanation
  21 도약설명        — leap_explanation
  22 교재근거위치    — "{source_file}:{line} ({status})" or status only
  23 출제의도        — intent
  24 보기글자수검증  — option_length_ok → "OK" / "위반"
  25 중복플래그      — duplicate_flag
  26 문제검증        — review_note (blank at generation time)
  27 채택상태        — adoption_status
  28 비고            — note

After writing, call ``finalize_xlsx(path, when)`` for byte-determinism
(strips openpyxl's runtime-stamped ``<dcterms:modified>``).  Both are
typically called together by the pipeline or tests.

Written atomically via ``examen.output.paths.atomic_write``.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
from paideia_shared.schemas import ExamItemDraft

from examen.output.paths import atomic_write

# ---------------------------------------------------------------------------
# Column header order — matches exam_draft_outputs.md exactly
# ---------------------------------------------------------------------------

_HEADERS = [
    "번호",           # 1
    "출처",           # 2
    "원본출처식별자",  # 3
    "챕터",           # 4
    "절",             # 5
    "주차",           # 6
    "핵심개념",        # 7
    "강조여부",        # 8
    "문제유형",        # 9
    "난이도",          # 10
    "문두방향",        # 11
    "문제",           # 12
    "보기1",          # 13
    "보기2",          # 14
    "보기3",          # 15
    "보기4",          # 16
    "보기5",          # 17
    "정답",           # 18
    "보기별오답근거",  # 19
    "오답설명",        # 20
    "도약설명",        # 21
    "교재근거위치",    # 22
    "출제의도",        # 23
    "보기글자수검증",  # 24
    "중복플래그",      # 25
    "문제검증",        # 26
    "채택상태",        # 27
    "비고",           # 28
]

if len(_HEADERS) != 28:  # pragma: no cover
    raise RuntimeError(f"_HEADERS must have 28 entries, got {len(_HEADERS)}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCE_LABELS: dict[str, str] = {
    "textbook": "교과서",
    "formative": "형성평가",
    "quiz": "퀴즈",
}


def _emphasis_label(item: ExamItemDraft) -> str:
    """Convert is_emphasized bool → Korean label."""
    if item.is_emphasized is True:
        return "강의강조"
    if item.is_emphasized is False:
        return "자습"
    return ""


def _evidence_cell(item: ExamItemDraft) -> str:
    """Format textbook_evidence as 'file:line (status)' or just status."""
    ev = item.textbook_evidence
    if ev is None:
        return ""
    if ev.line is not None:
        return f"{ev.source_file}:{ev.line} ({ev.status})"
    return f"({ev.status})"


def _option_length_label(item: ExamItemDraft) -> str:
    """Convert option_length_ok bool → 'OK' / '위반'."""
    return "OK" if item.option_length_ok else "위반"


def _row_values(item: ExamItemDraft) -> list[object]:
    """Flatten one ExamItemDraft to a list of 28 column values.

    Args:
        item: The exam item to flatten.

    Returns:
        List of 28 values in the canonical column order.
    """
    options = list(item.options)
    # Pad to 5 options if shorter (should never happen given schema, but defensive)
    while len(options) < 5:
        options.append("")

    distractor_joined = "\n".join(item.distractor_rationale)

    return [
        item.item_no,                                           # 1  번호
        _SOURCE_LABELS.get(item.source, item.source),          # 2  출처
        item.source_ref or "",                                  # 3  원본출처식별자
        item.chapter,                                           # 4  챕터
        item.section or "",                                     # 5  절
        item.week,                                              # 6  주차
        item.key_concept or "",                                 # 7  핵심개념
        _emphasis_label(item),                                  # 8  강조여부
        item.question_type,                                     # 9  문제유형
        item.difficulty,                                        # 10 난이도
        item.stem_polarity,                                     # 11 문두방향
        item.text,                                              # 12 문제
        options[0],                                             # 13 보기1
        options[1],                                             # 14 보기2
        options[2],                                             # 15 보기3
        options[3],                                             # 16 보기4
        options[4],                                             # 17 보기5
        item.answer_no,                                         # 18 정답
        distractor_joined,                                      # 19 보기별오답근거
        item.wrong_explanation,                                 # 20 오답설명
        item.leap_explanation,                                  # 21 도약설명
        _evidence_cell(item),                                   # 22 교재근거위치
        item.intent,                                            # 23 출제의도
        _option_length_label(item),                             # 24 보기글자수검증
        item.duplicate_flag,                                    # 25 중복플래그
        item.review_note,                                       # 26 문제검증
        item.adoption_status,                                   # 27 채택상태
        item.note or "",                                        # 28 비고
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_xlsx(items: list[ExamItemDraft], path: Path) -> None:
    """Write exam items to an xlsx file with the canonical 28-column layout.

    The file is written atomically (temp→rename).  Call
    ``finalize_xlsx(path, when)`` after this function for byte-determinism.

    Args:
        items: List of ExamItemDraft objects to write.
        path: Destination xlsx path.  Parent directory must exist.

    Note:
        This function alone does NOT guarantee byte-identical output across
        runs — openpyxl stamps ``<dcterms:modified>`` with the current time.
        Always pair with ``finalize_xlsx``.
    """
    def _write(tmp: Path) -> None:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "기말출제초안"

        # 헤더 행 작성
        ws.append(_HEADERS)

        # 데이터 행 작성
        for item in items:
            ws.append(_row_values(item))

        wb.save(tmp)

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, _write)


__all__ = ["write_xlsx"]
