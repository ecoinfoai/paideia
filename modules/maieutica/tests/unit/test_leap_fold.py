"""T039 — unit tests for ``maieutica.assemble.leap_fold``.

``lms_answer_explanation(item, max_len=None)`` returns the 답안설명 string for
the LMS ``.xls``:

- ``max_len is None`` or the combined fold already fits → the basic
  ``answer_explanation_combined`` is returned UNCHANGED.
- otherwise the LEAP portion is truncated first (with an ellipsis), keeping the
  ``{wrong} ─ 도약 ─ `` prefix and the wrong-explanation fully intact.

Crucially, the candidate is NEVER modified — overflow truncation is write-time
only, so the V4 invariant (``answer_explanation_combined`` == basic fold) always
holds on the candidate.
"""

from __future__ import annotations

from paideia_shared.schemas import QuizItemCandidate
from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation

_SEP = " ─ 도약 ─ "


def _candidate(wrong: str, leap_text: str) -> QuizItemCandidate:
    options = [f"보기 {i} 길이 충분한 보기 문자열 example padding" for i in range(1, 6)]
    return QuizItemCandidate(
        semester="2026-1",
        course_slug="anatomy",
        item_no=1,
        week=9,
        chapter_no=8,
        chapter="호흡계통",
        question_type="지식축적",
        difficulty="중",
        stem_polarity="부정형",
        text="문제",
        options=options,
        answer_no=3,
        option_evidence=[f"근거{i}" for i in range(1, 6)],
        wrong_explanation=wrong,
        leap=LeapExplanation(text=leap_text),
        answer_explanation_combined=f"{wrong}{_SEP}{leap_text}",
        option_length_ok=True,
        explanation_length_ok=True,
    )


def test_none_max_len_returns_basic_fold_unchanged() -> None:
    from maieutica.assemble.leap_fold import lms_answer_explanation

    item = _candidate("오답 설명", "도약 설명")
    assert lms_answer_explanation(item, max_len=None) == item.answer_explanation_combined


def test_fitting_combined_returned_unchanged() -> None:
    from maieutica.assemble.leap_fold import lms_answer_explanation

    item = _candidate("오답 설명", "도약 설명")
    # A generous max_len that the combined already fits within.
    assert (
        lms_answer_explanation(item, max_len=1000)
        == item.answer_explanation_combined
    )


def test_overflow_truncates_leap_first_keeping_wrong_intact() -> None:
    from maieutica.assemble.leap_fold import lms_answer_explanation

    wrong = "이것은 오답 설명입니다 정확히 보존되어야 함"
    leap = "이것은 매우 긴 도약 설명이며 잘려야 합니다 " * 5
    item = _candidate(wrong, leap)
    max_len = len(wrong) + len(_SEP) + 10  # only room for a sliver of leap
    out = lms_answer_explanation(item, max_len=max_len)

    # Fits the budget.
    assert len(out) <= max_len
    # Wrong-explanation + separator survive intact.
    assert out.startswith(f"{wrong}{_SEP}")
    # The leap portion was truncated (ends with an ellipsis), not the wrong part.
    leap_part = out[len(f"{wrong}{_SEP}") :]
    assert leap_part.endswith("…")
    assert leap_part != leap


def test_candidate_unchanged_after_truncation() -> None:
    """V4 must still hold: the candidate's combined stays the full basic fold."""
    from maieutica.assemble.leap_fold import lms_answer_explanation

    wrong = "오답 설명입니다"
    leap = "긴 도약 설명 " * 30
    item = _candidate(wrong, leap)
    before = item.answer_explanation_combined
    lms_answer_explanation(item, max_len=40)
    assert item.answer_explanation_combined == before
    assert item.leap.text == leap
    # V4 invariant intact on the candidate.
    assert item.answer_explanation_combined == f"{wrong}{_SEP}{leap}"


def test_truncation_is_deterministic() -> None:
    from maieutica.assemble.leap_fold import lms_answer_explanation

    item = _candidate("오답", "도약 설명 " * 50)
    a = lms_answer_explanation(item, max_len=30)
    b = lms_answer_explanation(item, max_len=30)
    assert a == b
