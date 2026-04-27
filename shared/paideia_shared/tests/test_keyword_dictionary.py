"""Contract tests for KeywordDictionary + load() helper (M8, FR-014/026)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from paideia_shared.keywords import KeywordDictionary, load
from pydantic import ValidationError


def test_default_ko_dictionary_loads() -> None:
    d = load("ko")
    assert d.language == "ko"
    assert d.version >= 1
    assert len(d.entries) >= 5
    categories = {e.category for e in d.entries}
    assert {"암기 부담", "시간 부족", "따라가기 어려움", "불안/심리", "기초 부족"} <= categories


def test_load_rejects_uppercase_language() -> None:
    with pytest.raises(ValueError, match="lowercase ISO 639-1"):
        load("KO")


def test_load_rejects_non_two_letter_language() -> None:
    with pytest.raises(ValueError, match="lowercase ISO 639-1"):
        load("kor")


def test_load_missing_language_raises_filenotfound() -> None:
    with pytest.raises(FileNotFoundError):
        load("zz")


def test_keyword_dictionary_rejects_duplicate_categories(tmp_path: Path) -> None:
    bad = {
        "language": "ko",
        "version": 1,
        "entries": [
            {"category": "암기 부담", "patterns": ["외우"]},
            {"category": "암기 부담", "patterns": ["기억"]},
        ],
    }
    with pytest.raises(ValidationError) as exc:
        KeywordDictionary.model_validate(bad)
    assert "V1" in str(exc.value)
    assert "duplicate" in str(exc.value)
    # exercise tmp_path roundtrip to make sure helper stays usable for fixtures
    f = tmp_path / "dup.yaml"
    f.write_text(yaml.safe_dump(bad), encoding="utf-8")
    assert f.exists()


def test_keyword_dictionary_rejects_invalid_language_pattern() -> None:
    with pytest.raises(ValidationError):
        KeywordDictionary.model_validate(
            {"language": "ko1", "version": 1, "entries": [{"category": "x", "patterns": ["x"]}]}
        )


def test_keyword_dictionary_rejects_empty_entries() -> None:
    with pytest.raises(ValidationError):
        KeywordDictionary.model_validate({"language": "ko", "version": 1, "entries": []})


def test_keyword_entry_rejects_empty_patterns() -> None:
    with pytest.raises(ValidationError):
        KeywordDictionary.model_validate(
            {
                "language": "ko",
                "version": 1,
                "entries": [{"category": "x", "patterns": []}],
            }
        )
