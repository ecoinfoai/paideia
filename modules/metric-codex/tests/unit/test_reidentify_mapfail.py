"""T037A RED — PRIV-05 fail-fast for re-identification.

validate_pseudonym_map rejects an empty or non-bijective map; reidentify_and_write
refuses to write any Gold file when the needed mapping is absent.
(FR-023 / PRIV-05: absent / corrupt / non-bijective.)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from metric_codex.errors import LocatedInputError
from metric_codex.generate.reidentify import (
    reidentify_and_write,
    validate_pseudonym_map,
)
from paideia_shared.schemas import PseudonymMapEntry


def _entry(sid: str, pseudonym: str, name_kr: str | None) -> PseudonymMapEntry:
    return PseudonymMapEntry(student_id=sid, name_kr=name_kr, pseudonym=pseudonym)


class TestValidatePseudonymMap:
    def test_empty_map_raises(self) -> None:
        with pytest.raises(LocatedInputError):
            validate_pseudonym_map([])

    def test_duplicate_pseudonym_raises(self) -> None:
        entries = [
            _entry("2026000001", "S001", "김철수"),
            _entry("2026000002", "S001", "이영희"),
        ]
        with pytest.raises(LocatedInputError):
            validate_pseudonym_map(entries)

    def test_duplicate_student_id_raises(self) -> None:
        entries = [
            _entry("2026000001", "S001", "김철수"),
            _entry("2026000001", "S002", "이영희"),
        ]
        with pytest.raises(LocatedInputError):
            validate_pseudonym_map(entries)

    def test_bijective_map_returns_index(self) -> None:
        entries = [
            _entry("2026000001", "S001", "김철수"),
            _entry("2026000002", "S002", "이영희"),
        ]
        index = validate_pseudonym_map(entries)
        assert set(index.keys()) == {"S001", "S002"}
        assert index["S001"].student_id == "2026000001"


class TestReidentifyAndWrite:
    def test_missing_pseudonym_raises_and_writes_nothing(self, tmp_path: Path) -> None:
        gold = tmp_path / "gold"
        index = validate_pseudonym_map([_entry("2026000001", "S001", "김철수")])

        with pytest.raises(LocatedInputError):
            reidentify_and_write(
                gold_dir=gold,
                pseudonym="S999",
                narrative="본문",
                pseudonym_index=index,
            )

        # PRIV-05: no partial Gold under 학생별/.
        student_dir = gold / "학생별"
        written = list(student_dir.glob("*.md")) if student_dir.is_dir() else []
        assert written == []

    def test_happy_path_writes_named_file(self, tmp_path: Path) -> None:
        gold = tmp_path / "gold"
        index = validate_pseudonym_map([_entry("2026000001", "S001", "김철수")])

        out = reidentify_and_write(
            gold_dir=gold,
            pseudonym="S001",
            narrative="## 요약\n근거 없음\n",
            pseudonym_index=index,
        )

        assert out == gold / "학생별" / "2026000001_김철수.md"
        assert out.read_text(encoding="utf-8") == "## 요약\n근거 없음\n"

    def test_name_kr_none_uses_student_id_only(self, tmp_path: Path) -> None:
        gold = tmp_path / "gold"
        index = validate_pseudonym_map([_entry("2026000002", "S002", None)])

        out = reidentify_and_write(
            gold_dir=gold,
            pseudonym="S002",
            narrative="본문\n",
            pseudonym_index=index,
        )

        assert out == gold / "학생별" / "2026000002.md"
        assert out.is_file()

    def test_name_kr_with_slash_raises_and_writes_nothing(self, tmp_path: Path) -> None:
        """I2: a name_kr with a path separator must fail fast (no escape from 학생별/)."""
        gold = tmp_path / "gold"
        index = validate_pseudonym_map([_entry("2026000003", "S003", "a/b")])

        with pytest.raises(LocatedInputError):
            reidentify_and_write(
                gold_dir=gold,
                pseudonym="S003",
                narrative="본문",
                pseudonym_index=index,
            )

        student_dir = gold / "학생별"
        written = list(student_dir.glob("*.md")) if student_dir.is_dir() else []
        assert written == []

    def test_name_kr_with_nul_raises(self, tmp_path: Path) -> None:
        """I2: a name_kr with a NUL byte must fail fast."""
        gold = tmp_path / "gold"
        index = validate_pseudonym_map([_entry("2026000004", "S004", "a\x00b")])

        with pytest.raises(LocatedInputError):
            reidentify_and_write(
                gold_dir=gold,
                pseudonym="S004",
                narrative="본문",
                pseudonym_index=index,
            )
