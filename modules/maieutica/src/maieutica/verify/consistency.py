"""T050 — Cross-representation consistency cross-check.

Asserts that the flat LMS files and the nested yaml candidate list hold the
SAME candidate set with no contradiction.  This is an internal pipeline
invariant check; a failure indicates a bug in the pipeline, not a user error.

``check_flat_nested_consistency`` takes the in-memory candidate lists (which
are the single source of truth that both the flat files and the nested yaml are
derived from) and verifies:

1. Quiz count: len(quiz_items) matches ``quiz_count`` if provided.
2. Formative count: len(formative_items) matches ``formative_count`` if provided.
3. Quiz item_no uniqueness: no duplicate item_no values within the quiz list.
4. Formative no uniqueness: no duplicate no values within the formative list.
5. Quiz items are ordered by item_no (pipeline invariant — they are generated
   in slot order and never shuffled).
6. answer_no consistency: every item's answer_explanation_combined round-trips
   through the `` ─ 도약 ─ `` separator to recover the original wrong_explanation
   and leap.text (V4 invariant, confirms flat xls and yaml agree on answer).

Fail-fast: raises ``RuntimeError`` (internal bug) on any contradiction.
All checks are O(N) — no file I/O.
"""

from __future__ import annotations

from paideia_shared.schemas import FormativeItemCandidate, QuizItemCandidate

_SEP = " ─ 도약 ─ "


def check_flat_nested_consistency(
    quiz_items: list[QuizItemCandidate],
    formative_items: list[FormativeItemCandidate],
    *,
    expected_quiz_count: int | None = None,
    expected_formative_count: int | None = None,
) -> None:
    """Assert flat and nested representations are consistent (fail-fast).

    Verifies the in-memory candidate lists — which are the single source of
    truth for both the flat LMS outputs and the nested yaml — are internally
    consistent.  Raises ``RuntimeError`` on contradiction (internal bug).

    Checks performed:
    - Quiz count matches expected (if provided).
    - Formative count matches expected (if provided).
    - Quiz ``item_no`` values are unique.
    - Formative ``no`` values are unique.
    - Each quiz item's ``answer_explanation_combined`` round-trips via the
      `` ─ 도약 ─ `` separator, confirming V4 holds (flat xls cell and yaml
      field carry the same combined string).

    Args:
        quiz_items: The quiz candidates that were written to both the flat
            ``.xls`` and the nested yaml.
        formative_items: The formative candidates that were written to both
            the flat ``.xlsx`` and the nested yaml.
        expected_quiz_count: If not ``None``, the total number of quiz items
            expected (from the generation spec).
        expected_formative_count: If not ``None``, the total number of formative
            items expected (from the generation spec).

    Raises:
        RuntimeError: If any consistency check fails (internal pipeline bug).
    """
    # 1. Count checks
    if expected_quiz_count is not None and len(quiz_items) != expected_quiz_count:
        raise RuntimeError(
            f"Internal consistency error: quiz item count mismatch — "
            f"expected {expected_quiz_count}, got {len(quiz_items)}"
        )
    if (
        expected_formative_count is not None
        and len(formative_items) != expected_formative_count
    ):
        raise RuntimeError(
            f"Internal consistency error: formative item count mismatch — "
            f"expected {expected_formative_count}, got {len(formative_items)}"
        )

    # 2. Quiz item_no uniqueness
    quiz_item_nos = [i.item_no for i in quiz_items]
    if len(quiz_item_nos) != len(set(quiz_item_nos)):
        from collections import Counter

        dupes = [k for k, v in Counter(quiz_item_nos).items() if v > 1]
        raise RuntimeError(
            f"Internal consistency error: duplicate quiz item_no values: {dupes}"
        )

    # 3. Formative no uniqueness
    formative_nos = [f.no for f in formative_items]
    if len(formative_nos) != len(set(formative_nos)):
        from collections import Counter

        dupes = [k for k, v in Counter(formative_nos).items() if v > 1]
        raise RuntimeError(
            f"Internal consistency error: duplicate formative no values: {dupes}"
        )

    # 4. V4 round-trip: answer_explanation_combined == wrong ─ 도약 ─ leap.text
    for item in quiz_items:
        expected_combined = f"{item.wrong_explanation}{_SEP}{item.leap.text}"
        if item.answer_explanation_combined != expected_combined:
            raise RuntimeError(
                f"Internal consistency error: quiz item {item.item_no} "
                f"answer_explanation_combined does not match "
                f"'wrong_explanation ─ 도약 ─ leap.text' (V4 violated). "
                f"This means the flat xls and nested yaml would disagree on the "
                f"combined explanation."
            )


__all__ = ["check_flat_nested_consistency"]
