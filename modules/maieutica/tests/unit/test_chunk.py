"""Unit tests for maieutica.silver.chunk — T021.

TDD: failing tests written BEFORE implementation (RED → GREEN).

Covers:
- chunk_id deterministic across runs (same chapter ⇒ identical ids).
- line_start/line_end are ORIGINAL line numbers.
- Section boundaries split the chapter correctly.
- text is the cleaned body (noise stripped by clean_textbook).
- removed_spans forwarded for audit.
"""

from __future__ import annotations

from paideia_shared.schemas import TextbookChunk

# ---------------------------------------------------------------------------
# Fixture: a small chapter with two numbered sections, noise, and an exercise
# block.  Section TOC entries appear once each (no duplicate TOC), so each
# heading is treated as a body heading.
# ---------------------------------------------------------------------------

FIXTURE_LINES: list[str] = [
    "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y",  # 1 — spaced header
    "제8장 호흡계통",  # 2 — running header
    "200",  # 3 — page number
    "",  # 4 — blank
    "1. 호흡기의 구조",  # 5 — section heading
    "코는 후각과 공기 가습을 담당한다.",  # 6 — body
    "인두는 소화계와 호흡계가 교차한다.",  # 7 — body
    "",  # 8 — blank
    "2. 가스 교환",  # 9 — section heading
    "폐포에서 산소와 이산화탄소가 교환된다.",  # 10 — body
    "",  # 11 — blank
    "연습문제",  # 12 — exercise block start
    "1. 코의 기능을 기술하시오.",  # 13
]


def _chunk() -> list[TextbookChunk]:
    from maieutica.silver.chunk import chunk_chapter

    return chunk_chapter(
        lines=FIXTURE_LINES,
        chapter_no=8,
        chapter="8장 호흡계통",
        semester="2026-1",
        course_slug="anatomy",
        source_file="8장 호흡계통.txt",
    )


class TestChunkChapter:
    def test_returns_textbook_chunks(self) -> None:
        chunks = _chunk()
        assert chunks
        assert all(isinstance(c, TextbookChunk) for c in chunks)

    def test_two_sections_detected(self) -> None:
        chunks = _chunk()
        sections = [c.section for c in chunks]
        assert sections == ["1. 호흡기의 구조", "2. 가스 교환"]

    def test_line_start_end_are_original(self) -> None:
        """line_start/line_end reference ORIGINAL fixture line numbers."""
        chunks = _chunk()
        first, second = chunks
        # Section 1 heading is original line 5; section 2 heading line 9.
        assert first.line_start == 5
        # Section 1 ends just before section 2 heading (line 8, the blank).
        assert first.line_end == 8
        assert second.line_start == 9

    def test_text_is_cleaned_body(self) -> None:
        """Cleaned text contains body lines, excludes noise & exercises."""
        chunks = _chunk()
        first = chunks[0]
        assert "코는 후각과 공기 가습을 담당한다." in first.text
        assert "인두는 소화계와 호흡계가 교차한다." in first.text
        # Noise / exercise content must not leak into any chunk text.
        joined = "\n".join(c.text for c in chunks)
        assert "연습문제" not in joined
        assert "제8장 호흡계통" not in joined
        assert "200" not in joined

    def test_removed_spans_present(self) -> None:
        chunks = _chunk()
        # Every chunk carries the same audit log (forwarded from the cleaner).
        assert chunks[0].removed_spans
        assert any("연습문제" in s for s in chunks[0].removed_spans)

    def test_chunk_id_deterministic_across_runs(self) -> None:
        """Same chapter ⇒ identical chunk_ids on repeated invocation."""
        ids_a = [c.chunk_id for c in _chunk()]
        ids_b = [c.chunk_id for c in _chunk()]
        assert ids_a == ids_b
        # IDs are non-empty and unique per section.
        assert all(ids_a)
        assert len(set(ids_a)) == len(ids_a)

    def test_fallback_single_chunk_when_no_sections(self) -> None:
        from maieutica.silver.chunk import chunk_chapter

        lines = [
            "코는 후각과 공기 가습을 담당한다.",
            "폐포에서 가스 교환이 일어난다.",
        ]
        chunks = chunk_chapter(
            lines=lines,
            chapter_no=8,
            chapter="8장 호흡계통",
            semester="2026-1",
            course_slug="anatomy",
            source_file="8장 호흡계통.txt",
        )
        assert len(chunks) == 1
        assert chunks[0].section is None
        assert chunks[0].line_start == 1
        assert chunks[0].line_end == 2
