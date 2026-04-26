"""Unit tests for normalize_student_id."""

from __future__ import annotations

import pytest
from immersio.normalize import normalize_student_id


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026194999", "2026194999"),
        (2026194999, "2026194999"),
        (" 2026194999 ", "2026194999"),
        ('"2026194999"', "2026194999"),
        ("'2026194999'", "2026194999"),
        ("2026-1949-99", "2026194999"),
        ("\t2026194999\n", "2026194999"),
    ],
)
def test_normalize_positive(raw: object, expected: str) -> None:
    assert normalize_student_id(raw) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw",
    ["123456789", "12345678901", "abcdefghij", "2026!94999", "2026 19a 999"],
)
def test_normalize_negative_value(raw: str) -> None:
    with pytest.raises(ValueError, match="normalize_student_id"):
        normalize_student_id(raw)


@pytest.mark.parametrize("raw", [2026194999.0, True, None, ["2026194999"], object()])
def test_normalize_negative_type(raw: object) -> None:
    with pytest.raises(TypeError, match="expected str or int"):
        normalize_student_id(raw)  # type: ignore[arg-type]


def test_normalize_idempotent() -> None:
    once = normalize_student_id(" '2026-194-999' ")
    twice = normalize_student_id(once)
    assert once == twice == "2026194999"
