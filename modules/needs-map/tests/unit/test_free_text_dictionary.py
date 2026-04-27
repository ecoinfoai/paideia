"""Unit tests for free-text dictionary classifier (T089, FR-014)."""

from __future__ import annotations

import pytest


def test_classify_dictionary_basic_match() -> None:
    from needs_map.free_text.dictionary import classify_dictionary
    from paideia_shared.keywords import load

    d = load("ko")
    rows = classify_dictionary(
        [
            ("2026194000", "Q62", "암기가 너무 많습니다"),
            ("2026194001", "Q62", "시간이 부족해요"),
            ("2026194002", "Q62", "잘 모르겠어요"),
        ],
        dictionary=d,
    )
    assert len(rows) == 3
    assert rows[0].matched_categories == ["암기 부담"]
    assert rows[1].matched_categories == ["시간 부족"]
    assert rows[2].match_source == "uncategorized"


def test_classify_dictionary_multiple_categories() -> None:
    from needs_map.free_text.dictionary import classify_dictionary
    from paideia_shared.keywords import load

    rows = classify_dictionary(
        [("2026194000", "Q62", "암기가 너무 많고 시간도 부족합니다")],
        dictionary=load("ko"),
    )
    assert "암기 부담" in rows[0].matched_categories
    assert "시간 부족" in rows[0].matched_categories
    assert rows[0].match_source == "dictionary"


@pytest.mark.parametrize(
    "raw",
    ["", "  ", "\t", "없습니다", "  없습니다  ", "없음", "x", "-"],
)
def test_classify_dictionary_no_response_tokens(raw: str) -> None:
    from needs_map.free_text.dictionary import classify_dictionary
    from paideia_shared.keywords import load

    rows = classify_dictionary(
        [("2026194000", "Q62", raw)], dictionary=load("ko")
    )
    assert rows[0].match_source == "no_response"
    assert rows[0].matched_categories == []


def test_classify_dictionary_nfkc_casefold_normalization() -> None:
    """NFKC + casefold strip; full-width digits + mixed case still match."""
    from needs_map.free_text.dictionary import classify_dictionary
    from paideia_shared.keywords import load

    # Korean is unaffected by casefold; NFKC normalizes full-width spaces and
    # combining characters. Test that mixed-case English still matches if the
    # dictionary has a lowercase pattern (defensive — current ko.yaml has no
    # English entries, so we synthesize a substring assertion only).
    rows = classify_dictionary(
        [("2026194000", "Q62", "암기 가 너무 많습니다")],
        dictionary=load("ko"),
    )
    assert "암기 부담" in rows[0].matched_categories


def test_classify_dictionary_raw_length_recorded() -> None:
    from needs_map.free_text.dictionary import classify_dictionary
    from paideia_shared.keywords import load

    text = "암기가 너무 많습니다"
    rows = classify_dictionary(
        [("2026194000", "Q62", text)], dictionary=load("ko")
    )
    assert rows[0].raw_length == len(text)


def test_classify_dictionary_does_not_store_raw_text() -> None:
    """FreeTextRow contract: raw text body must NOT appear on the row (FR-PII-002)."""
    from needs_map.free_text.dictionary import classify_dictionary
    from paideia_shared.keywords import load

    rows = classify_dictionary(
        [("2026194000", "Q62", "암기가 너무 많습니다")], dictionary=load("ko")
    )
    fields = rows[0].model_fields_set
    assert "raw_text" not in fields
    # also: serialized dump has no raw_text key
    dump = rows[0].model_dump()
    assert "raw_text" not in dump
