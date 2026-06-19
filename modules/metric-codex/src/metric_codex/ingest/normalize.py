"""T027 — 학번 (student ID) normalization for metric-codex ingest.

This module IS the ingest boundary for student identifiers.  Every value
that enters the pipeline must pass through ``normalize_student_id`` exactly
once.  The function never returns a malformed ID and never silently drops
invalid input.
"""

from __future__ import annotations

import math

from metric_codex.errors import LocatedInputError

# Column label used in located errors — the 학번 column has a canonical name.
_STUDENT_ID_COLUMN = "학번"
_EXPECTED_FORM = "10-digit student id"
_MAX_DIGITS = 10


def normalize_student_id(
    raw: str | int | float,
    *,
    source: str,
    row: int | None = None,
) -> str:
    """Normalize an Excel-origin student ID value to a 10-digit string.

    Accepts values as they appear after openpyxl reads a cell: Python ``int``,
    ``float`` (must be integral), or ``str``.  The normalized result matches
    the ``CanonicalStudentId`` pattern ``^\\d{10}$``.

    Normalization steps:
    1. Convert numeric types: ``float`` → reject if not integral; then convert
       ``int``/integral ``float`` to its integer string (no trailing ``.0``).
    2. Strip surrounding whitespace from the string value.
    3. Validate: non-empty, all digits, length ≤ 10.
    4. Left-zero-pad to exactly 10 digits.

    Args:
        raw: The raw cell value from openpyxl (str, int, or float).
        source: File name or path for error location context.
        row: 1-based row number in the source file (optional).

    Returns:
        Zero-padded 10-digit student ID string (e.g. ``"2026000003"``).

    Raises:
        LocatedInputError: If the value is a non-integral float, contains
            non-digit characters after cleaning, is empty/blank, or exceeds
            10 digits.  The error names ``source``, ``row``, the student-ID
            column, the expected form, and the offending value.
    """
    # ------------------------------------------------------------------
    # Step 1: normalise numeric types to a digit string
    # ------------------------------------------------------------------
    if isinstance(raw, float):
        if not math.isfinite(raw) or raw != math.floor(raw):
            raise LocatedInputError(
                "non-integral float is not a valid student ID",
                file=source,
                row=row,
                column=_STUDENT_ID_COLUMN,
                expected=_EXPECTED_FORM,
                actual=str(raw),
            )
        cleaned = str(int(raw))
    elif isinstance(raw, int):
        cleaned = str(raw)
    else:
        # str path
        cleaned = str(raw).strip()

    # ------------------------------------------------------------------
    # Step 2: strip whitespace (str path already done above; safe to skip
    # for numeric paths since str(int) never has whitespace)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Step 3: validate
    # ------------------------------------------------------------------
    if not cleaned:
        raise LocatedInputError(
            "empty or whitespace-only student ID",
            file=source,
            row=row,
            column=_STUDENT_ID_COLUMN,
            expected=_EXPECTED_FORM,
            actual=repr(raw),
        )

    if not cleaned.isdigit():
        raise LocatedInputError(
            "student ID contains non-digit characters",
            file=source,
            row=row,
            column=_STUDENT_ID_COLUMN,
            expected=_EXPECTED_FORM,
            actual=cleaned,
        )

    if len(cleaned) > _MAX_DIGITS:
        raise LocatedInputError(
            f"student ID has {len(cleaned)} digits (maximum {_MAX_DIGITS})",
            file=source,
            row=row,
            column=_STUDENT_ID_COLUMN,
            expected=_EXPECTED_FORM,
            actual=cleaned,
        )

    # ------------------------------------------------------------------
    # Step 4: zero-pad to exactly 10 digits
    # ------------------------------------------------------------------
    return cleaned.zfill(_MAX_DIGITS)


__all__ = ["normalize_student_id"]
