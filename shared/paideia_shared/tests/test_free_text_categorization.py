"""Contract tests for FreeTextRow (T076, M6)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas import FreeTextRow
from pydantic import ValidationError


def _row(**overrides: object) -> FreeTextRow:
    base: dict[str, object] = {
        "student_id": "2026194042",
        "item_id": "Q62_anxiety_freetext",
        "matched_categories": ["불안/심리"],
        "match_source": "dictionary",
        "raw_length": 18,
    }
    base.update(overrides)
    return FreeTextRow(**base)  # type: ignore[arg-type]


def test_dictionary_match_with_categories() -> None:
    row = _row()
    assert row.match_source == "dictionary"
    assert row.matched_categories == ["불안/심리"]


def test_no_response_requires_empty_categories() -> None:
    row = _row(match_source="no_response", matched_categories=[])
    assert row.matched_categories == []


def test_no_response_with_categories_rejected() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(match_source="no_response", matched_categories=["불안/심리"])


@pytest.mark.parametrize(
    "source", ["dictionary", "llm", "llm_fallback", "no_response", "uncategorized"]
)
def test_match_source_enum_5_values(source: str) -> None:
    if source == "no_response":
        row = _row(match_source=source, matched_categories=[])
    else:
        row = _row(match_source=source)
    assert row.match_source == source


def test_match_source_other_value_rejected() -> None:
    with pytest.raises(ValidationError):
        _row(match_source="manual")


def test_raw_length_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        _row(raw_length=-1)


def test_raw_length_zero_allowed() -> None:
    row = _row(match_source="no_response", matched_categories=[], raw_length=0)
    assert row.raw_length == 0


def test_multiple_matched_categories_preserved() -> None:
    row = _row(matched_categories=["암기 부담", "시간 부족"])
    assert row.matched_categories == ["암기 부담", "시간 부족"]


def test_empty_category_string_rejected() -> None:
    with pytest.raises(ValidationError):
        _row(matched_categories=[""])


def test_uncategorized_with_empty_list_allowed() -> None:
    row = _row(match_source="uncategorized", matched_categories=[])
    assert row.match_source == "uncategorized"
    assert row.matched_categories == []
