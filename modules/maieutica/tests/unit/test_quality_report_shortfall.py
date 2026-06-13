"""T026 (RED) — unit tests for the shortfall / subsection-spread report sections.

Covers ``contracts/quality_report_shortfall.md`` Q1–Q3 + QR1–QR3:

- **Q1 (요청 vs 산출)**: a "요청 N / 산출 M" row; ⚠️ marker when M < N.
- **Q2 (소절 분산)**: per-subsection adopted-count table (label → count ≤3).
  Single-subsection fallback → "소절 미검출(단일 소절)".
- **Q3 (부족분·사유)**: when M < N the shortfall N−M is decomposed into the three
  causes (가용 소절 부족 / 중복 제거 / 미확인 제외), each stated, summing to N−M.
- **QR1 (no silent omission)**: every M<N case shows shortfall + causes.
- **QR2 (backward-compat)**: no-shortfall call is byte-identical to before — the
  existing section headers present, new section headers absent.
- **QR3 (determinism)**: same input → identical Markdown.
"""

from __future__ import annotations

from maieutica.output.quality_report import QuizShortfall, build_quality_report
from paideia_shared.schemas import (
    LeapExplanation,
    MaieuticaTextbookEvidence,
    QuizItemCandidate,
)

# Existing section headers (QR2 backward-compat anchor).
_EXISTING_HEADERS = [
    "## 총 문항 수",
    "## 정답 번호 분포",
    "## 줄기 극성 분포",
    "## 난이도 분포",
    "## 교재 근거 확인",
    "## 형성평가 요약",
    "## 주의 항목",
]
# New section headers (must be ABSENT when no shortfall is passed).
_NEW_HEADERS = ["## 요청 대비 산출", "## 소절 분산", "## 부족분 사유"]


def _confirmed_evidence(line: int) -> MaieuticaTextbookEvidence:
    return MaieuticaTextbookEvidence(
        chunk_id="chunk-1",
        source_file="ch8.txt",
        line=line,
        found_text="확인된 본문",
        status="확인",
    )


def _make_item(*, item_no: int = 1, answer_no: int = 1) -> QuizItemCandidate:
    leap_text = "다음 개념으로의 도약 설명입니다."
    wrong = "오답 설명입니다."
    leap = LeapExplanation(text=leap_text, textbook_evidence=None)
    options = [
        f"{marker} 충분한 길이를 가진 보기 문장입니다 {item_no}-{i} abcde"
        for i, marker in enumerate("①②③④⑤", start=1)
    ]
    return QuizItemCandidate(
        semester="2026-1",
        course_slug="anatomy",
        item_no=item_no,
        week=9,
        chapter_no=8,
        chapter="8장 호흡계통",
        section="1. 코의 구조",
        key_concept=f"개념-{item_no}",
        question_type="지식축적",
        difficulty="중",
        stem_polarity="부정형",
        text=f"{item_no}번 문제: 다음 중 옳지 않은 것은?",
        options=options,
        answer_no=answer_no,
        option_evidence=["근거"] * 5,
        wrong_explanation=wrong,
        leap=leap,
        textbook_evidence=_confirmed_evidence(item_no),
        answer_explanation_combined=f"{wrong} ─ 도약 ─ {leap_text}",
        option_length_ok=True,
        explanation_length_ok=True,
        duplicate_flag=False,
        review_note="",
        adoption_status="생성",
        note=None,
    )


# ---------------------------------------------------------------------------
# Q1 / Q3 — capacity-only shortfall
# ---------------------------------------------------------------------------


def test_q1_q3_capacity_short() -> None:
    """N=15, M=9, capacity_short=6 → 요청/산출 rows, ⚠️ 부족분 6, capacity cause."""
    items = [_make_item(item_no=i) for i in range(1, 10)]  # M = 9
    shortfall = QuizShortfall(
        requested=15,
        produced=9,
        capacity_short=6,
        dedup_removed=0,
        unconfirmed_excluded=0,
        available_subsections=3,
        subsection_counts={"1) 코": 3, "2) 인두": 3, "3) 후두": 3},
        single_subsection=False,
    )
    md = build_quality_report(items, [], shortfall=shortfall)

    assert "## 요청 대비 산출" in md
    assert "15" in md and "9" in md
    assert "⚠️" in md
    # ⚠️ 부족분 6 line present (QR1).
    assert "6" in md
    assert "## 부족분 사유" in md
    # capacity cause stated with the TRUE available subsection count (3 × 3 = 9).
    assert "가용 소절 부족" in md
    assert "소절 3개 × cap 3 = 9 < 15" in md
    # The three displayed causes must sum to N−M = 6.
    assert _shortfall_causes_sum(md) == 6


def test_q3_mixed_causes_sum_to_n_minus_m() -> None:
    """N=12, M=9: dedup 2 + 미확인 1 (capacity 0) → causes sum to 3."""
    items = [_make_item(item_no=i) for i in range(1, 10)]  # M = 9
    shortfall = QuizShortfall(
        requested=12,
        produced=9,
        capacity_short=0,
        dedup_removed=2,
        unconfirmed_excluded=1,
        available_subsections=3,
        subsection_counts={"1) 코": 3, "2) 인두": 3, "3) 후두": 3},
        single_subsection=False,
    )
    md = build_quality_report(items, [], shortfall=shortfall)

    assert "## 부족분 사유" in md
    assert "중복 제거" in md
    assert "미확인 제외" in md
    assert _shortfall_causes_sum(md) == 3


def test_q3_capacity_label_uses_available_not_adopted_when_produced_zero() -> None:
    """M=0 corner: empty subsection_counts must NOT zero out the capacity label.

    A single-subsection chapter where every item is 미확인-excluded leaves
    produced=0 and subsection_counts={}, but the available subsection count is 1,
    so the label must read "소절 1개 × cap 3 = 3 < 8" (not "소절 0개 × cap 3 = 3").
    """
    shortfall = QuizShortfall(
        requested=8,
        produced=0,
        capacity_short=5,  # N=8, capacity = 1×3 = 3 → 5 short
        dedup_removed=0,
        unconfirmed_excluded=3,  # the 3 produced were all 미확인-excluded
        available_subsections=1,
        subsection_counts={},  # produced==0 → empty adopted grouping
        single_subsection=False,
    )
    md = build_quality_report([], [], shortfall=shortfall)

    assert "## 부족분 사유" in md
    # True available subsection count (1), NOT the empty adopted grouping (0).
    assert "소절 1개 × cap 3 = 3 < 8" in md
    assert "소절 0개" not in md
    # Causes still sum to N−M = 8.
    assert _shortfall_causes_sum(md) == 8


# ---------------------------------------------------------------------------
# Q2 — subsection spread
# ---------------------------------------------------------------------------


def test_q2_subsection_counts_rendered_and_capped() -> None:
    items = [_make_item(item_no=i) for i in range(1, 10)]
    counts = {"1) 코": 3, "2) 인두": 3, "3) 후두": 3}
    shortfall = QuizShortfall(
        requested=9,
        produced=9,
        capacity_short=0,
        dedup_removed=0,
        unconfirmed_excluded=0,
        available_subsections=3,
        subsection_counts=counts,
        single_subsection=False,
    )
    md = build_quality_report(items, [], shortfall=shortfall)
    assert "## 소절 분산" in md
    for label, cnt in counts.items():
        assert label in md
        assert cnt <= 3


def test_q2_single_subsection_fallback() -> None:
    items = [_make_item(item_no=i) for i in range(1, 4)]
    shortfall = QuizShortfall(
        requested=3,
        produced=3,
        capacity_short=0,
        dedup_removed=0,
        unconfirmed_excluded=0,
        available_subsections=1,
        subsection_counts={"chunk-1": 3},
        single_subsection=True,
    )
    md = build_quality_report(items, [], shortfall=shortfall)
    assert "소절 미검출(단일 소절)" in md


# ---------------------------------------------------------------------------
# QR1 — no silent omission (every M<N case shows shortfall + causes)
# ---------------------------------------------------------------------------


def test_qr1_every_short_case_lists_causes() -> None:
    items = [_make_item(item_no=i) for i in range(1, 10)]
    shortfall = QuizShortfall(
        requested=11,
        produced=9,
        capacity_short=1,
        dedup_removed=0,
        unconfirmed_excluded=1,
        available_subsections=3,
        subsection_counts={"1) 코": 3, "2) 인두": 3, "3) 후두": 3},
        single_subsection=False,
    )
    md = build_quality_report(items, [], shortfall=shortfall)
    assert "## 부족분 사유" in md
    assert _shortfall_causes_sum(md) == 2


# ---------------------------------------------------------------------------
# M == N — no shortfall section (충족)
# ---------------------------------------------------------------------------


def test_m_equals_n_no_shortfall_causes() -> None:
    items = [_make_item(item_no=i) for i in range(1, 4)]
    shortfall = QuizShortfall(
        requested=3,
        produced=3,
        capacity_short=0,
        dedup_removed=0,
        unconfirmed_excluded=0,
        available_subsections=1,
        subsection_counts={"1) 코": 3},
        single_subsection=False,
    )
    md = build_quality_report(items, [], shortfall=shortfall)
    assert "## 부족분 사유" not in md
    assert "충족" in md


# ---------------------------------------------------------------------------
# QR2 — backward-compat (no shortfall kwarg → existing sections, no new ones)
# ---------------------------------------------------------------------------


def test_qr2_backward_compat_no_shortfall_kwarg() -> None:
    items = [_make_item(item_no=i) for i in range(1, 4)]
    md = build_quality_report(items, [])
    for header in _EXISTING_HEADERS:
        assert header in md, f"missing existing header {header}"
    for header in _NEW_HEADERS:
        assert header not in md, f"new header {header} leaked without shortfall"


# ---------------------------------------------------------------------------
# QR3 — determinism (same input → identical Markdown)
# ---------------------------------------------------------------------------


def test_qr3_determinism() -> None:
    items = [_make_item(item_no=i) for i in range(1, 10)]
    shortfall = QuizShortfall(
        requested=12,
        produced=9,
        capacity_short=0,
        dedup_removed=2,
        unconfirmed_excluded=1,
        available_subsections=3,
        subsection_counts={"1) 코": 3, "2) 인두": 3, "3) 후두": 3},
        single_subsection=False,
    )
    a = build_quality_report(items, [], shortfall=shortfall)
    b = build_quality_report(items, [], shortfall=shortfall)
    assert a == b


# ---------------------------------------------------------------------------
# helper — extract the displayed nonzero causes and sum their counts
# ---------------------------------------------------------------------------


def _shortfall_causes_sum(md: str) -> int:
    """Sum the integer count attached to each displayed shortfall cause line.

    Parses the lines under "## 부족분 사유": each cause line is a bullet that
    states a "<count>건" total for that cause; the parsed counts must sum to N−M.
    """
    import re

    in_section = False
    total = 0
    for line in md.splitlines():
        if line.startswith("## 부족분 사유"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.lstrip().startswith("-"):
            # Take the LAST "<n>건" on the line as the cause total.
            matches = re.findall(r"(\d+)\s*건", line)
            if matches:
                total += int(matches[-1])
    return total
