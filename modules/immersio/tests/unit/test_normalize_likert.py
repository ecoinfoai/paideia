"""Unit tests for normalize_likert."""

from __future__ import annotations

import pytest
from immersio.normalize import normalize_likert


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("매우 그렇다", 7),
        ("매우그렇다", 7),
        ("매우　그렇다", 7),  # full-width space (U+3000)
        ("그렇다", 6),
        ("약간 그렇다", 5),
        ("보통이다", 4),
        ("보통", 4),
        ("약간 아니다", 3),
        ("약간 그렇지 않다", 3),
        ("아니다", 2),
        ("그렇지 않다", 2),
        ("매우 아니다", 1),
        ("매우 그렇지 않다", 1),
        ("  매우 그렇다  ", 7),  # outer whitespace
        ("매우  그렇다", 7),  # collapsed inner whitespace
    ],
)
def test_normalize_positive(raw: str, expected: int) -> None:
    assert normalize_likert(raw) == expected


@pytest.mark.parametrize("raw", ["매우 좋아요", "그렇네요", "no", "", "agree"])
def test_normalize_negative_value(raw: str) -> None:
    with pytest.raises(ValueError, match="undefined Likert text"):
        normalize_likert(raw)


@pytest.mark.parametrize("raw", [7, None, 5.0, ["매우 그렇다"]])
def test_normalize_negative_type(raw: object) -> None:
    with pytest.raises(TypeError, match="expected str"):
        normalize_likert(raw)  # type: ignore[arg-type]
