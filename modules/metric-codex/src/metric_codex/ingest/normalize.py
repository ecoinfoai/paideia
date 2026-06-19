"""T027 — 학번 (student ID) normalization for metric-codex ingest.

This module IS the ingest boundary for student identifiers.  Every value
that enters the pipeline must pass through ``normalize_student_id`` exactly
once.  The function never returns a malformed ID and never silently drops
invalid input.
"""

from __future__ import annotations

import math
import re

from metric_codex.errors import LocatedInputError

# Column label used in located errors — the 학번 column has a canonical name.
_STUDENT_ID_COLUMN = "학번"
_EXPECTED_FORM = "10-digit student id"
_MAX_DIGITS = 10

# ASCII-only digit matcher. ``str.isdigit()`` returns True for non-ASCII
# unicode digits (Arabic-Indic, Bengali, fullwidth, …) which would slip past
# the unicode-aware ``^\d{10}$`` pattern and silently corrupt the canonical id.
# This module is the authoritative ASCII boundary for the 학번.
_ASCII_DIGITS = re.compile(r"[0-9]+")


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
    1. Reject ``bool`` (an ``int`` subclass that would otherwise stringify).
    2. Convert numeric types: ``float`` → reject if not integral; then convert
       ``int``/integral ``float`` to its integer string (no trailing ``.0``).
    3. Strip surrounding whitespace from the string value.
    4. Validate: non-empty, ASCII digits only, length ≤ 10.
    5. Left-zero-pad to exactly 10 digits.

    Args:
        raw: The raw cell value from openpyxl (str, int, or float).
        source: File name or path for error location context.
        row: 1-based row number in the source file (optional).

    Returns:
        Zero-padded 10-digit student ID string (e.g. ``"2026000003"``).

    Raises:
        LocatedInputError: If the value is a bool, a non-integral float,
            contains non-ASCII-digit characters after cleaning, is empty/blank,
            or exceeds 10 digits.  The error names ``source``, ``row``, the
            student-ID column, the expected form, and the offending value
            (rendered with ``repr`` so invisible whitespace is visible).
    """
    # bool is an int subclass; ``str(True)`` == "True" would otherwise reach the
    # non-digit branch with a confusing message — reject it explicitly here.
    if isinstance(raw, bool):
        raise LocatedInputError(
            "boolean is not a valid student id",
            file=source,
            row=row,
            column=_STUDENT_ID_COLUMN,
            expected=_EXPECTED_FORM,
            actual=repr(raw),
        )

    # Normalise numeric types to a candidate digit string.
    if isinstance(raw, float):
        if not math.isfinite(raw) or raw != math.floor(raw):
            raise LocatedInputError(
                "non-integral float is not a valid student id",
                file=source,
                row=row,
                column=_STUDENT_ID_COLUMN,
                expected=_EXPECTED_FORM,
                actual=repr(raw),
            )
        cleaned = str(int(raw))
    elif isinstance(raw, int):
        cleaned = str(raw)
    else:
        cleaned = str(raw).strip()

    # Validate: non-empty, ASCII digits only, length ≤ 10.
    if not cleaned:
        raise LocatedInputError(
            "empty or whitespace-only student id",
            file=source,
            row=row,
            column=_STUDENT_ID_COLUMN,
            expected=_EXPECTED_FORM,
            actual=repr(raw),
        )

    if not _ASCII_DIGITS.fullmatch(cleaned):
        raise LocatedInputError(
            "student id contains non-ASCII-digit characters",
            file=source,
            row=row,
            column=_STUDENT_ID_COLUMN,
            expected=_EXPECTED_FORM,
            actual=repr(raw),
        )

    if len(cleaned) > _MAX_DIGITS:
        raise LocatedInputError(
            f"student id has {len(cleaned)} digits (maximum {_MAX_DIGITS})",
            file=source,
            row=row,
            column=_STUDENT_ID_COLUMN,
            expected=_EXPECTED_FORM,
            actual=repr(raw),
        )

    # Restore leading zeros Excel dropped: left-pad to exactly 10 digits.
    return cleaned.zfill(_MAX_DIGITS)


__all__ = ["normalize_student_id"]
