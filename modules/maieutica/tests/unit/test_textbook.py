"""Unit tests for maieutica.ingest.textbook — T018.

TDD: failing tests written BEFORE implementation (RED → GREEN).

Covers:
- load_chapter: (lineno, text) pairs are 1-based; line numbers are sequential;
  blank lines are included; char offsets computed from cumulative line lengths.
- Missing file → FileNotFoundError with path in message.
- Char offset correctness: a known substring can be located in the original text
  using the reported char_offset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Shared fixture text (same style as examen's textbook fixture)
# ---------------------------------------------------------------------------

FIXTURE_LINES: list[str] = [
    "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y",  # 1 — spaced header
    "제8장 호흡계통",  # 2 — running header
    "C H A P T E R  8",  # 3 — spaced header
    "200",  # 4 — page number
    "",  # 5 — blank
    "1. 호흡기의 구조",  # 6 — section heading
    "",  # 7
    "코는 후각과 공기 가습을 담당한다.",  # 8 — body
    "인두는 소화계와 호흡계가 교차한다.",  # 9 — body
    "",  # 10
    "201",  # 11 — page number
    "",  # 12
    "연습문제",  # 13 — exercise block start
    "1. 코의 기능을 기술하시오.",  # 14
]

FIXTURE_TEXT: str = "\n".join(FIXTURE_LINES)


# ============================================================================
# T018 — load_chapter
# ============================================================================


class TestLoadChapter:
    def _write_fixture(self, tmp_path: Path) -> Path:
        p = tmp_path / "8장 호흡계통.txt"
        p.write_text(FIXTURE_TEXT, encoding="utf-8")
        return p

    def test_returns_list_of_tuples(self, tmp_path: Path) -> None:
        """load_chapter returns a list of (int, str) tuples."""
        from maieutica.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_line_numbers_are_one_based(self, tmp_path: Path) -> None:
        """First entry has lineno == 1."""
        from maieutica.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        assert result[0][0] == 1

    def test_line_count_matches_fixture(self, tmp_path: Path) -> None:
        """Number of returned entries == number of lines in the fixture."""
        from maieutica.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        assert len(result) == len(FIXTURE_LINES)

    def test_line_numbers_are_sequential(self, tmp_path: Path) -> None:
        """Line numbers are strictly sequential from 1."""
        from maieutica.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        for i, (lineno, _) in enumerate(result):
            assert lineno == i + 1

    def test_blank_lines_preserved(self, tmp_path: Path) -> None:
        """Blank lines appear in the result (line numbers must not skip)."""
        from maieutica.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        # Line 5 in the fixture is blank
        lineno, text = result[4]
        assert lineno == 5
        assert text == ""

    def test_text_content_matches_fixture(self, tmp_path: Path) -> None:
        """Text in each entry matches the corresponding fixture line."""
        from maieutica.ingest.textbook import load_chapter

        p = self._write_fixture(tmp_path)
        result = load_chapter(p)
        for i, (lineno, text) in enumerate(result):
            assert text == FIXTURE_LINES[i], (
                f"line {lineno}: expected {FIXTURE_LINES[i]!r}, got {text!r}"
            )

    def test_missing_file_raises_with_path(self, tmp_path: Path) -> None:
        """Missing .txt file → FileNotFoundError whose message includes the path."""
        from maieutica.ingest.textbook import load_chapter

        missing = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError, match=str(missing)):
            load_chapter(missing)

    def test_file_ending_with_newline(self, tmp_path: Path) -> None:
        """A file ending with '\\n' does NOT produce an extra empty final entry."""
        from maieutica.ingest.textbook import load_chapter

        p = tmp_path / "test.txt"
        p.write_text("line1\nline2\n", encoding="utf-8")
        result = load_chapter(p)
        # Should be 2 lines, not 3
        assert len(result) == 2
        assert result[0] == (1, "line1")
        assert result[1] == (2, "line2")


# ============================================================================
# T018 — char_offset correctness
# The task requires preserving char offsets so evidence anchoring (T022)
# can point at original positions.  load_chapter works line-by-line; the
# char offset of line N is sum(len(line_k) + 1 for k in 1..N-1) for
# newline-separated text.  We verify this property here.
# ============================================================================


class TestCharOffsets:
    """Char-offset computation derived from the (lineno, text) pairs.

    load_chapter itself returns (lineno, text) pairs.  The test verifies that,
    given those pairs, the caller can faithfully reconstruct the char offset of
    any line in the original file — i.e. the text is ORIGINAL and unmodified.
    """

    def test_char_offset_of_first_line_is_zero(self, tmp_path: Path) -> None:
        """The first line starts at char offset 0 in the file."""
        from maieutica.ingest.textbook import load_chapter

        p = tmp_path / "8장 호흡계통.txt"
        p.write_text(FIXTURE_TEXT, encoding="utf-8")
        lines = load_chapter(p)

        # Reconstruct the full text from (lineno, text) pairs
        reconstructed = "\n".join(text for _, text in lines)
        # The first line's text must appear at offset 0
        first_text = lines[0][1]
        assert reconstructed.startswith(first_text)
        assert reconstructed.index(first_text) == 0

    def test_known_substring_offset_verifiable(self, tmp_path: Path) -> None:
        """Given (lineno, text) pairs, a known substring's char offset is findable.

        Specifically: '코는 후각과 공기 가습을 담당한다.' is line 8 in FIXTURE_LINES.
        Its char offset in the original file equals sum of len(line) + 1 for
        lines 1..7 (the newline-joined representation).
        """
        from maieutica.ingest.textbook import load_chapter

        p = tmp_path / "8장 호흡계통.txt"
        p.write_text(FIXTURE_TEXT, encoding="utf-8")
        lines = load_chapter(p)

        target_text = "코는 후각과 공기 가습을 담당한다."
        # Find the (lineno, text) entry whose text matches
        matches = [(ln, t) for ln, t in lines if t == target_text]
        assert len(matches) == 1, f"Expected 1 match, got {matches}"
        lineno, text = matches[0]
        assert lineno == 8

        # Compute expected char offset: sum of (len + 1 for newline) for lines 1..7
        expected_offset = sum(len(t) + 1 for _, t in lines if _ < 8)
        # Verify against the actual file content
        raw = p.read_text(encoding="utf-8")
        actual_offset = raw.index(target_text)
        assert actual_offset == expected_offset, (
            f"char offset mismatch: expected {expected_offset}, actual {actual_offset}"
        )
