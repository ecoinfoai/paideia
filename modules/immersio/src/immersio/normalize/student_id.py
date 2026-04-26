"""Student ID normalization to canonical 10-digit zero-padded string."""

from __future__ import annotations

import re

_STRIP_PATTERN = re.compile(r"[\s'\"-]+")
_CANONICAL_PATTERN = re.compile(r"^\d{10}$")


def normalize_student_id(value: str | int) -> str:
    """Normalize a student ID to canonical 10-digit zero-padded string.

    Args:
        value: Raw student ID. Strings may include surrounding whitespace,
            quotation marks, or hyphens. Integers are converted via str().
            Floats are rejected because Excel autocoercion can lose precision
            (research.md §10).

    Returns:
        Canonical student ID matching r"^\\d{10}$" (e.g. "2026194999").

    Raises:
        TypeError: If value is not str or int (notably bool/float).
        ValueError: If the cleaned value is not exactly 10 digits.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise TypeError(
            f"normalize_student_id: expected str or int, got "
            f"{type(value).__name__} ({value!r})."
        )
    raw = str(value)
    cleaned = _STRIP_PATTERN.sub("", raw)
    if not _CANONICAL_PATTERN.match(cleaned):
        raise ValueError(
            f"normalize_student_id: cannot canonicalize {value!r}; "
            f"expected exactly 10 digits after stripping whitespace, quotes, "
            f"and hyphens, found {cleaned!r} (len={len(cleaned)})."
        )
    return cleaned
