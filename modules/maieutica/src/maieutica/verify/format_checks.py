"""T029 — Format verification: option/explanation length, duplicates, answer dist.

quiz_gen (T027) freezes provisional ``option_length_ok`` /
``explanation_length_ok`` flags.  This stage is the AUTHORITY for those soft
flags (FR-008/009/010/011): it (re)computes and sets them via ``model_copy``,
flags near-duplicate candidates sharing a ``key_concept``, and RECORDS the
answer_no distribution for the manifest.

What maieutica does NOT do
--------------------------
maieutica only *records* the answer_no distribution — it never rebalances
answer keys.  Answer/difficulty *balance* is examen's job (FR-015); contrast
``examen.verify.format_checks.balance_answer_keys`` which is deliberately
absent here.

All functions are non-raising — violations are flagged on the returned
candidate, never crash the pipeline.  Frozen model → ``model_copy`` only.
"""

from __future__ import annotations

from paideia_shared.schemas import QuizItemCandidate

# Option length window (codepoints, incl. spaces / number prefix) — FR-010.
_OPTION_MIN_LEN = 30
_OPTION_MAX_LEN = 50

# Explanation length ceiling (codepoints, incl. spaces) — FR-011.
_EXPLANATION_MAX_LEN = 200


def _compute_option_length_ok(options: list[str]) -> bool:
    """Return True iff every option is 30–50 codepoints (incl. spaces).

    Args:
        options: The option strings (each includes its number prefix).

    Returns:
        ``True`` iff ``options`` is non-empty and each option's codepoint
        length is within ``[30, 50]``.
    """
    if not options:
        return False
    return all(_OPTION_MIN_LEN <= len(opt) <= _OPTION_MAX_LEN for opt in options)


def _compute_explanation_length_ok(wrong_explanation: str, leap_text: str) -> bool:
    """Return True iff wrong_explanation and leap_text are each <=200 codepoints.

    Args:
        wrong_explanation: The wrong-answer explanation.
        leap_text: The leap explanation body.

    Returns:
        ``True`` iff both strings are at most ``200`` codepoints (incl. spaces).
    """
    return (
        len(wrong_explanation) <= _EXPLANATION_MAX_LEN
        and len(leap_text) <= _EXPLANATION_MAX_LEN
    )


def check_format(item: QuizItemCandidate) -> QuizItemCandidate:
    """Authoritatively (re)compute ``option_length_ok`` / ``explanation_length_ok``.

    Overrides whatever provisional values quiz_gen stored (the verify stage owns
    these soft flags) and returns a NEW frozen candidate via ``model_copy``.

    Args:
        item: The quiz candidate to format-check.

    Returns:
        A NEW ``QuizItemCandidate`` with recalculated ``option_length_ok`` and
        ``explanation_length_ok``.
    """
    option_length_ok = _compute_option_length_ok(list(item.options))
    explanation_length_ok = _compute_explanation_length_ok(
        item.wrong_explanation, item.leap.text
    )
    return item.model_copy(
        update={
            "option_length_ok": option_length_ok,
            "explanation_length_ok": explanation_length_ok,
        }
    )


def detect_duplicates(items: list[QuizItemCandidate]) -> list[QuizItemCandidate]:
    """Flag near-duplicate candidates by shared ``key_concept`` (FR-008).

    Candidates sharing the same non-None ``key_concept`` are potential
    duplicates.  The *first* occurrence is kept (``duplicate_flag`` unchanged);
    every subsequent candidate with the same concept is flagged
    (``duplicate_flag=True``).

    Design:
    - ``key_concept=None`` candidates are NEVER grouped (no signal).
    - Candidates already carrying ``duplicate_flag=True`` keep it.
    - Deterministic: stable input order → stable output flags.

    Args:
        items: Quiz candidates (order is preserved).

    Returns:
        A new list of the same length; later duplicates have ``duplicate_flag=True``.
    """
    seen: set[str] = set()
    result: list[QuizItemCandidate] = []
    for item in items:
        kc = item.key_concept
        if kc is not None and kc in seen:
            if not item.duplicate_flag:
                item = item.model_copy(update={"duplicate_flag": True})
        elif kc is not None:
            seen.add(kc)
        result.append(item)
    return result


def answer_no_distribution(items: list[QuizItemCandidate]) -> dict[int, int]:
    """Record the answer_no distribution for the manifest (no rebalancing).

    maieutica only records the distribution; rebalancing answer keys is
    examen's responsibility (FR-015).  This function reads ``answer_no`` and
    never alters any candidate.

    Args:
        items: Quiz candidates whose ``answer_no`` values are counted.

    Returns:
        A dict mapping each answer position ``1..5`` to its count (positions
        with no candidate map to ``0``).
    """
    distribution = dict.fromkeys(range(1, 6), 0)
    for item in items:
        distribution[item.answer_no] += 1
    return distribution


__all__ = ["answer_no_distribution", "check_format", "detect_duplicates"]
