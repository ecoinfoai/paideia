"""Unit tests for expand_multiselect."""

from __future__ import annotations

import pytest
from immersio.normalize import expand_multiselect


def test_single_option() -> None:
    assert expand_multiselect("신경계") == ["신경계"]


def test_multiple_options_preserves_order() -> None:
    assert expand_multiselect("신경계;근육계;소화계") == ["신경계", "근육계", "소화계"]


def test_strips_whitespace() -> None:
    assert expand_multiselect("신경계 ; 근육계 ; 소화계") == ["신경계", "근육계", "소화계"]


def test_empty_input_returns_empty_list() -> None:
    assert expand_multiselect("") == []


def test_only_separator_returns_empty_list() -> None:
    assert expand_multiselect(";;;") == []


def test_drops_empty_tokens() -> None:
    assert expand_multiselect("신경계;;근육계;") == ["신경계", "근육계"]


def test_custom_separator() -> None:
    assert expand_multiselect("a|b|c", separator="|") == ["a", "b", "c"]


def test_deterministic_repeated_call() -> None:
    raw = "신경계;근육계;소화계"
    first = expand_multiselect(raw)
    second = expand_multiselect(raw)
    assert first == second


@pytest.mark.parametrize("raw", [None, 7, ["신경계"]])
def test_type_error(raw: object) -> None:
    with pytest.raises(TypeError, match="expected str"):
        expand_multiselect(raw)  # type: ignore[arg-type]
