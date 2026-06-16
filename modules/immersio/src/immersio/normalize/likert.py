"""Korean Likert text to 1-7 integer canonical mapping."""

from __future__ import annotations

import re
import unicodedata
from typing import Final

LIKERT_TEXT_TO_INT: Final[dict[str, int]] = {
    "매우 그렇다": 7,
    "그렇다": 6,
    "약간 그렇다": 5,
    "보통이다": 4,
    "보통": 4,
    "약간 아니다": 3,
    "약간 그렇지 않다": 3,
    "아니다": 2,
    "그렇지 않다": 2,
    "매우 아니다": 1,
    "매우 그렇지 않다": 1,
}
"""Canonical seven-point Likert table (research.md §9)."""

_WHITESPACE_PATTERN = re.compile(r"\s+")


def _canonicalize(text: str) -> str:
    """NFKC normalize, strip outer whitespace, collapse runs of inner whitespace."""
    nfkc = unicodedata.normalize("NFKC", text)
    return _WHITESPACE_PATTERN.sub(" ", nfkc.strip())


_TABLE_CANONICAL: Final[dict[str, int]] = {
    _canonicalize(k): v for k, v in LIKERT_TEXT_TO_INT.items()
}
_TABLE_NO_SPACE: Final[dict[str, int]] = {
    _canonicalize(k).replace(" ", ""): v for k, v in LIKERT_TEXT_TO_INT.items()
}


def normalize_likert(text: str) -> int:
    """Map a Korean Likert response to an integer in [1, 7].

    Args:
        text: Free-form Korean response (e.g. "매우 그렇다", "매우그렇다",
            "매우　그렇다" with full-width whitespace).

    Returns:
        Integer 1..7 per LIKERT_TEXT_TO_INT.

    Raises:
        TypeError: If text is not a str.
        ValueError: If text is not in the canonical vocabulary.
    """
    if not isinstance(text, str):
        raise TypeError(f"normalize_likert: expected str, got {type(text).__name__} ({text!r}).")
    canonical = _canonicalize(text)
    if canonical in _TABLE_CANONICAL:
        return _TABLE_CANONICAL[canonical]
    no_space = canonical.replace(" ", "")
    if no_space in _TABLE_NO_SPACE:
        return _TABLE_NO_SPACE[no_space]
    raise ValueError(
        f"normalize_likert: undefined Likert text {text!r} (canonical={canonical!r}); "
        f"expected one of {sorted(LIKERT_TEXT_TO_INT.keys())}."
    )
