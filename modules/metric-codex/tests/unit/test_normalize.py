"""T026 — Unit tests for normalize_student_id (RED first, then GREEN).

Tests written before implementation per TDD mandate.

Covers:
- Happy path: 10-digit string passthrough
- Zero-padding: 9-digit and shorter inputs padded to 10 digits
- Whitespace stripping: leading/trailing spaces
- int input (openpyxl numeric cell as Python int)
- float input that is integral (e.g. 2026000003.0)
- Error paths: letters in value → LocatedInputError
- Error paths: non-ASCII unicode digits → LocatedInputError (C1)
- Error paths: bool input → LocatedInputError (m2)
- Error paths: length > 10 digits → LocatedInputError
- Error paths: empty / whitespace-only → LocatedInputError
- Error paths: non-integral float (e.g. 2026.5) → LocatedInputError
- Error messages include source name and offending value
"""

from __future__ import annotations

import re

import pytest
from metric_codex.errors import LocatedInputError
from metric_codex.ingest.normalize import normalize_student_id

# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_ten_digit_str_passthrough() -> None:
    """10-digit string passes through unchanged."""
    result = normalize_student_id("2026000003", source="test.xlsx", row=2)
    assert result == "2026000003"


def test_nine_digit_str_zero_padded() -> None:
    """9-digit string is left-zero-padded to 10 digits."""
    result = normalize_student_id("202600001", source="test.xlsx", row=3)
    assert result == "0202600001"


def test_eight_digit_str_zero_padded() -> None:
    """8-digit string is left-zero-padded to 10 digits."""
    result = normalize_student_id("20260001", source="test.xlsx", row=4)
    assert result == "0020260001"


def test_one_digit_str_zero_padded() -> None:
    """Single-digit string is left-zero-padded to 10 digits."""
    result = normalize_student_id("1", source="test.xlsx", row=5)
    assert result == "0000000001"


def test_leading_trailing_whitespace_stripped() -> None:
    """Leading/trailing whitespace is stripped before normalization."""
    result = normalize_student_id("  2026000003  ", source="test.xlsx", row=6)
    assert result == "2026000003"


def test_whitespace_with_short_id() -> None:
    """Whitespace stripped, then short ID is zero-padded."""
    result = normalize_student_id("  202600001  ", source="test.xlsx", row=7)
    assert result == "0202600001"


def test_int_input() -> None:
    """Python int (openpyxl numeric cell) is converted to zero-padded string."""
    result = normalize_student_id(2026000003, source="grades.xlsx", row=10)
    assert result == "2026000003"


def test_int_input_short() -> None:
    """Python int with fewer than 10 digits is zero-padded."""
    result = normalize_student_id(202600001, source="grades.xlsx", row=11)
    assert result == "0202600001"


def test_float_integral_input() -> None:
    """Float that represents an integer (e.g. 2026000003.0) is accepted."""
    result = normalize_student_id(2026000003.0, source="grades.xlsx", row=12)
    assert result == "2026000003"


def test_float_integral_input_short() -> None:
    """Integral float with fewer than 10 digits is zero-padded."""
    result = normalize_student_id(26000003.0, source="grades.xlsx", row=13)
    assert result == "0026000003"


def test_result_matches_canonical_pattern() -> None:
    """All normalized results match the CanonicalStudentId pattern ^\\d{10}$."""
    pattern = re.compile(r"^\d{10}$")
    cases: list[str | int | float] = [
        "2026000003",
        "202600001",
        "  2026000003  ",
        2026000003,
        2026000003.0,
        "1",
    ]
    for raw in cases:
        result = normalize_student_id(raw, source="test.xlsx", row=1)
        assert pattern.match(result), (
            f"Result {result!r} does not match ^\\d{{10}}$ for input {raw!r}"
        )


def test_row_none_allowed() -> None:
    """row=None is valid (column-level source, no specific row)."""
    result = normalize_student_id("2026000003", source="test.xlsx", row=None)
    assert result == "2026000003"


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


def test_letters_in_id_raises() -> None:
    """Non-digit characters (letters) raise LocatedInputError."""
    with pytest.raises(LocatedInputError):
        normalize_student_id("20260A0003", source="bad.xlsx", row=2)


def test_letters_error_contains_source() -> None:
    """LocatedInputError message includes the source file name."""
    with pytest.raises(LocatedInputError) as exc_info:
        normalize_student_id("20260A0003", source="bad.xlsx", row=2)
    assert "bad.xlsx" in str(exc_info.value)


def test_letters_error_contains_offending_value() -> None:
    """LocatedInputError message includes the offending value."""
    with pytest.raises(LocatedInputError) as exc_info:
        normalize_student_id("20260A0003", source="bad.xlsx", row=2)
    assert "20260A0003" in str(exc_info.value)


# ---------------------------------------------------------------------------
# C1 — non-ASCII unicode digits must be rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unicode_digits",
    [
        "٠١٢٣٤٥٦٧٨٩",  # Arabic-Indic digits (U+0660..U+0669)
        "０１２３４５６７８９",  # Fullwidth digits (U+FF10..U+FF19)
        "০১২৩৪৫৬৭৮৯",  # Bengali digits (U+09E6..U+09EF)
    ],
)
def test_non_ascii_unicode_digits_raise(unicode_digits: str) -> None:
    """10-char strings of non-ASCII unicode digits raise LocatedInputError.

    ``str.isdigit()`` returns True for these, and the unicode-aware ``^\\d{10}$``
    pattern matches them too — so without an explicit ASCII guard they would
    silently corrupt the canonical id (C1).
    """
    assert len(unicode_digits) == 10  # guard: these really are 10 'digit' chars
    with pytest.raises(LocatedInputError):
        normalize_student_id(unicode_digits, source="unicode.xlsx", row=2)


def test_non_ascii_digit_error_contains_source() -> None:
    """LocatedInputError for unicode digits includes the source name."""
    with pytest.raises(LocatedInputError) as exc_info:
        normalize_student_id("٠١٢٣٤٥٦٧٨٩", source="unicode.xlsx", row=2)
    assert "unicode.xlsx" in str(exc_info.value)


# ---------------------------------------------------------------------------
# m2 — bool input must be rejected (bool is an int subclass)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [True, False])
def test_bool_input_raises(value: bool) -> None:
    """Boolean input raises LocatedInputError (bool is an int subclass)."""
    with pytest.raises(LocatedInputError):
        normalize_student_id(value, source="bool.xlsx", row=2)


def test_bool_error_contains_source() -> None:
    """LocatedInputError for bool includes the source name."""
    with pytest.raises(LocatedInputError) as exc_info:
        normalize_student_id(True, source="bool.xlsx", row=2)
    assert "bool.xlsx" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Length / empty / float error paths
# ---------------------------------------------------------------------------


def test_length_over_ten_raises() -> None:
    """11+ digit string raises LocatedInputError (too long for any valid ID)."""
    with pytest.raises(LocatedInputError):
        normalize_student_id("20260000031", source="bad.xlsx", row=3)


def test_length_over_ten_error_contains_source() -> None:
    """LocatedInputError for >10 digits includes source name."""
    with pytest.raises(LocatedInputError) as exc_info:
        normalize_student_id("20260000031", source="long.xlsx", row=3)
    assert "long.xlsx" in str(exc_info.value)


def test_empty_string_raises() -> None:
    """Empty string raises LocatedInputError."""
    with pytest.raises(LocatedInputError):
        normalize_student_id("", source="empty.xlsx", row=4)


def test_whitespace_only_raises() -> None:
    """Whitespace-only string raises LocatedInputError."""
    with pytest.raises(LocatedInputError):
        normalize_student_id("   ", source="empty.xlsx", row=5)


def test_whitespace_error_contains_source() -> None:
    """LocatedInputError for empty/blank includes source name."""
    with pytest.raises(LocatedInputError) as exc_info:
        normalize_student_id("   ", source="blank.xlsx", row=5)
    assert "blank.xlsx" in str(exc_info.value)


def test_non_integral_float_raises() -> None:
    """Non-integral float (e.g. 2026.5) raises LocatedInputError."""
    with pytest.raises(LocatedInputError):
        normalize_student_id(2026.5, source="bad.xlsx", row=6)


def test_non_integral_float_error_contains_source() -> None:
    """LocatedInputError for non-integral float includes source name."""
    with pytest.raises(LocatedInputError) as exc_info:
        normalize_student_id(2026.5, source="fractional.xlsx", row=6)
    assert "fractional.xlsx" in str(exc_info.value)


def test_non_integral_float_error_contains_value() -> None:
    """LocatedInputError for non-integral float includes the offending value."""
    with pytest.raises(LocatedInputError) as exc_info:
        normalize_student_id(2026.5, source="fractional.xlsx", row=6)
    assert "2026.5" in str(exc_info.value)


def test_located_input_error_is_value_error() -> None:
    """LocatedInputError is a subclass of ValueError (CLI exit-2 trap)."""
    with pytest.raises(ValueError):
        normalize_student_id("BAD", source="x.xlsx", row=1)
