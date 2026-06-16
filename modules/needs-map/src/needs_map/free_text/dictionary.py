"""Free-text dictionary classifier (T095, FR-014, FR-016).

NFKC + casefold + strip normalization on both input and patterns; substring
match preserves all categories whose any pattern hits the normalized text.
Empty / NO_RESPONSE_TOKENS strings yield ``match_source='no_response'`` with
empty ``matched_categories`` (M6 V1 invariant).

PII hygiene (FR-PII-002): only the character length of the raw text is stored
(``raw_length``); the body itself is dropped after classification.
"""

from __future__ import annotations

import unicodedata

from paideia_shared.keywords import KeywordDictionary
from paideia_shared.schemas import FreeTextRow

# Normalised tokens that count as "no substantive response".
_NO_RESPONSE_TOKENS: frozenset[str] = frozenset({"", "없습니다", "없음", "x", "-", "n/a", "na"})


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().strip()


def classify_dictionary(
    responses: list[tuple[str, str, str]],
    dictionary: KeywordDictionary,
) -> list[FreeTextRow]:
    """Classify each (student_id, item_id, raw_text) triple.

    Args:
        responses: List of ``(student_id, item_id, raw_text)`` tuples.
            ``raw_text`` may be empty / whitespace / ``없습니다`` etc. — all
            map to ``match_source='no_response'``.
        dictionary: Loaded :class:`KeywordDictionary` (e.g. via
            ``paideia_shared.keywords.load("ko")``).

    Returns:
        One :class:`FreeTextRow` per input triple, in input order.
    """
    rows: list[FreeTextRow] = []
    for student_id, item_id, raw in responses:
        normalized = _normalize(raw)
        raw_length = len(raw)

        if normalized in _NO_RESPONSE_TOKENS:
            rows.append(
                FreeTextRow(
                    student_id=student_id,
                    item_id=item_id,
                    matched_categories=[],
                    match_source="no_response",
                    raw_length=raw_length,
                )
            )
            continue

        matched: list[str] = []
        for entry in dictionary.entries:
            for pattern in entry.patterns:
                if _normalize(pattern) in normalized:
                    matched.append(entry.category)
                    break  # one hit per category is enough

        if matched:
            rows.append(
                FreeTextRow(
                    student_id=student_id,
                    item_id=item_id,
                    matched_categories=matched,
                    match_source="dictionary",
                    raw_length=raw_length,
                )
            )
        else:
            rows.append(
                FreeTextRow(
                    student_id=student_id,
                    item_id=item_id,
                    matched_categories=[],
                    match_source="uncategorized",
                    raw_length=raw_length,
                )
            )
    return rows
