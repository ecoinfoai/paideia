"""T039 — LMS 답안설명 fold with write-time leap-first overflow truncation.

``lms_answer_explanation(item, max_len=None) -> str`` returns the string written
to the LMS ``.xls`` 답안설명 cell.  By default (``max_len is None``) it returns
``item.answer_explanation_combined`` verbatim — the BASIC fold
``f"{wrong} ─ 도약 ─ {leap.text}"`` (B1: unlimited).

Write-time truncation only (V4 invariant)
-----------------------------------------
``QuizItemCandidate`` enforces V4:
``answer_explanation_combined == f"{wrong_explanation} ─ 도약 ─ {leap.text}"``.
So overflow truncation must NEVER be stored on the candidate; it is applied only
here, at write time, and only to the returned string.  The candidate (and the
full-fidelity yaml) always keep the complete leap.

When the combined fold exceeds ``max_len`` the LEAP portion is truncated FIRST:
the ``{wrong} ─ 도약 ─ `` prefix and the wrong-explanation are preserved intact,
and as much of ``leap.text`` as fits (followed by a single ``…`` ellipsis) is
appended.  If even the prefix does not fit ``max_len``, the prefix is returned
truncated to ``max_len`` (the smallest possible string the LMS will accept).
"""

from __future__ import annotations

from paideia_shared.schemas import QuizItemCandidate

# The canonical separator between wrong-explanation and leap (matches V4).
_SEPARATOR = " ─ 도약 ─ "
_ELLIPSIS = "…"


def lms_answer_explanation(
    item: QuizItemCandidate,
    max_len: int | None = None,
) -> str:
    """Return the 답안설명 cell string for ``item``, truncating the leap first.

    Args:
        item: The quiz candidate.  Never modified.
        max_len: Maximum character length for the cell, or ``None`` for no limit
            (the default — B1).  When the combined fold already fits, it is
            returned unchanged regardless of this value.

    Returns:
        ``item.answer_explanation_combined`` unchanged when ``max_len is None``
        or the fold fits; otherwise the wrong-explanation + separator followed
        by a leap fragment truncated with a trailing ``…`` so the result length
        is ``<= max_len``.
    """
    combined = item.answer_explanation_combined
    if max_len is None or len(combined) <= max_len:
        return combined

    prefix = f"{item.wrong_explanation}{_SEPARATOR}"
    if len(prefix) + len(_ELLIPSIS) > max_len:
        # Not even room for the prefix + ellipsis → return the prefix clipped to
        # the budget (smallest acceptable string).
        return prefix[:max_len]

    leap_budget = max_len - len(prefix) - len(_ELLIPSIS)
    return f"{prefix}{item.leap.text[:leap_budget]}{_ELLIPSIS}"


__all__ = ["lms_answer_explanation"]
