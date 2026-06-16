"""Keyword dictionary loader + language-mismatch detection (T022).

Thin wrapper around ``paideia_shared.keywords.load`` plus a sample-based
match-rate computation used by the pipeline to set
``NeedsMapManifest.dictionary_language_mismatch_warning`` (FR-023, adversary P-7).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from paideia_shared.keywords import KeywordDictionary, load


def load_keywords(language: str = "ko") -> KeywordDictionary:
    """Load the packaged keyword dictionary by ISO 639-1 code.

    Thin pass-through to :func:`paideia_shared.keywords.load` so the needs-map
    pipeline can swap the loader (e.g. for fixture-based testing) without
    touching the shared package.
    """
    return load(language)


def _normalize(text: str) -> str:
    """NFKC + casefold + strip — matches free_text/dictionary normalization."""
    return unicodedata.normalize("NFKC", text).casefold().strip()


def compute_match_rate(dictionary: KeywordDictionary, sample_responses: Iterable[str]) -> float:
    """Fraction of ``sample_responses`` that match at least one dictionary entry.

    Empty / whitespace-only responses are excluded from the denominator so the
    rate reflects substantive responses only. Used by the pipeline to detect
    "dictionary language mismatch" (FR-023, adversary P-7) when the sample
    match rate falls below the operational threshold (typically 0.3).

    Args:
        dictionary: Loaded :class:`KeywordDictionary`.
        sample_responses: Iterable of raw response strings (PII not
            pre-stripped — keyword matching does not store the strings).

    Returns:
        Match rate in ``[0.0, 1.0]``. Returns ``0.0`` if the sample contains
        no substantive responses.
    """
    normalized_patterns: list[str] = []
    for entry in dictionary.entries:
        normalized_patterns.extend(_normalize(p) for p in entry.patterns)

    substantive = 0
    matched = 0
    for raw in sample_responses:
        text = _normalize(raw)
        if not text:
            continue
        substantive += 1
        if any(pattern in text for pattern in normalized_patterns):
            matched += 1

    if substantive == 0:
        return 0.0
    return matched / substantive
