"""Unit tests for multi-level textbook chunking — T004 (RED) → T005 (GREEN).

Binding contract: ``specs/010-maieutica-quiz-diversity/contracts/chunking.md``
(C1–C6).  Asserted against the fixture pair:

- ``modules/maieutica/tests/fixtures/multi_level_chapter.txt`` (52 lines)
- ``modules/maieutica/tests/fixtures/multi_level_chapter.README.md`` (the
  line-by-line structure contract these assertions mirror).

C1 granularity · C2 oversized sub-split · C3 line ranges · C4 fallback ·
C5 determinism · C6 TOC dedup.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import TextbookChunk

# Generation-spec values from the fixture README (§ Companion fixture).
_SEMESTER = "2026-1"
_COURSE = "anatomy"
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "multi_level_chapter.txt"


def _fixture_lines() -> list[str]:
    """Read the multi-level fixture as a list of lines (newlines stripped)."""
    return _FIXTURE.read_text(encoding="utf-8").splitlines()


def _chunk() -> list[TextbookChunk]:
    from maieutica.silver.chunk import chunk_chapter

    return chunk_chapter(
        lines=_fixture_lines(),
        chapter_no=_CHAPTER_NO,
        chapter=_CHAPTER,
        semester=_SEMESTER,
        course_slug=_COURSE,
        source_file="multi_level_chapter.txt",
    )


class TestC1Granularity:
    """C1 — descend to the deepest heading at every level present."""

    def test_more_than_two_top_level_chunks(self) -> None:
        chunks = _chunk()
        # v0.1.0 (N. only) produced exactly 2 chunks; multi-level must exceed.
        assert len(chunks) > 2

    def test_deeper_headings_each_become_a_subsection(self) -> None:
        chunks = _chunk()
        sections = [c.section for c in chunks]
        # Every L1/L2/L3 heading (after TOC dedup) is its own subsection.
        for expected in (
            "1. 호흡계통의 구조",
            "1) 코",
            "2) 인두",
            "3) 후두",
            "가) 성대",
            "나) 후두덮개",
            "2. 호흡의 조절",
            "1) 가스 교환",
            "① 중추 조절",
            "② 화학 조절",
        ):
            assert expected in sections, f"missing subsection {expected!r}"

    def test_known_subsection_line_ranges(self) -> None:
        chunks = _chunk()
        by_section: dict[str, TextbookChunk] = {}
        for c in chunks:
            # Oversized 1) 가스 교환 is sub-split; skip its duplicate label here.
            if c.section is not None and c.section not in by_section:
                by_section[c.section] = c
        # (section, line_start, line_end) per fixture README heading map.
        expected_ranges = {
            "1. 호흡계통의 구조": (8, 10),
            "1) 코": (11, 14),
            "2) 인두": (15, 18),
            "3) 후두": (19, 20),
            "가) 성대": (21, 22),
            "나) 후두덮개": (23, 25),
            "2. 호흡의 조절": (26, 28),
            "① 중추 조절": (44, 45),
            "② 화학 조절": (46, 47),
        }
        for section, (start, end) in expected_ranges.items():
            chunk = by_section[section]
            assert chunk.line_start == start, section
            assert chunk.line_end == end, section


class TestC2OversizedSubSplit:
    """C2 — oversized ``1) 가스 교환`` paragraph-split at blank lines."""

    def test_oversized_subsection_split_into_multiple_chunks(self) -> None:
        chunks = _chunk()
        pieces = [c for c in chunks if c.section == "1) 가스 교환"]
        assert len(pieces) >= 2

    def test_sub_pieces_tile_lines_29_to_43_contiguously(self) -> None:
        chunks = _chunk()
        pieces = sorted(
            (c for c in chunks if c.section == "1) 가스 교환"),
            key=lambda c: c.line_start,
        )
        # First piece begins at the heading line; last ends at subsection end.
        assert pieces[0].line_start == 29
        assert pieces[-1].line_end == 43
        # Contiguous, non-overlapping tiling across the sub-pieces.
        for prev, nxt in zip(pieces, pieces[1:], strict=False):
            assert prev.line_end < nxt.line_start
            assert nxt.line_start == prev.line_end + 1

    def test_sub_piece_chunk_ids_unique(self) -> None:
        chunks = _chunk()
        ids = [c.chunk_id for c in chunks]
        assert len(set(ids)) == len(ids)


class TestC3LineRanges:
    """C3 — ordered, non-overlapping ranges; one chunk per body line."""

    def test_ranges_ordered_and_non_overlapping(self) -> None:
        chunks = _chunk()
        for c in chunks:
            assert c.line_start <= c.line_end
        for prev, nxt in zip(chunks, chunks[1:], strict=False):
            assert prev.line_end < nxt.line_start

    def test_known_body_line_covered_by_exactly_one_chunk(self) -> None:
        chunks = _chunk()
        # Line 16 ("인두는 공기와 음식이 함께 지나가는 통로이다.") body of 2) 인두.
        lineno = 16
        covering = [c for c in chunks if c.line_start <= lineno <= c.line_end]
        assert len(covering) == 1
        assert covering[0].section == "2) 인두"


class TestC4Fallback:
    """C4 — no numbered heading → single whole-chapter chunk, section=None."""

    def test_fallback_single_chunk_when_no_headings(self) -> None:
        from maieutica.silver.chunk import chunk_chapter

        lines = [
            "코는 후각과 공기 가습을 담당한다.",
            "폐포에서 가스 교환이 일어난다.",
        ]
        chunks = chunk_chapter(
            lines=lines,
            chapter_no=_CHAPTER_NO,
            chapter=_CHAPTER,
            semester=_SEMESTER,
            course_slug=_COURSE,
            source_file="multi_level_chapter.txt",
        )
        assert len(chunks) == 1
        assert chunks[0].section is None


class TestC5Determinism:
    """C5 — identical input ⇒ byte-identical chunk list."""

    def test_chunk_ids_identical_across_runs(self) -> None:
        ids_a = [c.chunk_id for c in _chunk()]
        ids_b = [c.chunk_id for c in _chunk()]
        assert ids_a == ids_b

    def test_full_chunk_tuples_identical_across_runs(self) -> None:
        def signature(c: TextbookChunk) -> tuple[object, ...]:
            return (c.chunk_id, c.section, c.line_start, c.line_end, c.text)

        sig_a = [signature(c) for c in _chunk()]
        sig_b = [signature(c) for c in _chunk()]
        assert sig_a == sig_b


class TestC6TocDedup:
    """C6 — first (TOC) occurrence of a repeated heading is skipped."""

    def test_toc_copies_skipped(self) -> None:
        chunks = _chunk()
        # The TOC copies live on lines 5–6; no chunk may start there.
        starts = {c.line_start for c in chunks}
        assert 5 not in starts
        assert 6 not in starts
        # The body L1 headings (lines 8, 26) are the kept ones.
        assert 8 in starts
        assert 26 in starts

    def test_no_duplicate_top_level_subsection(self) -> None:
        chunks = _chunk()
        l1_sections = [
            c.section for c in chunks if c.section in ("1. 호흡계통의 구조", "2. 호흡의 조절")
        ]
        assert l1_sections.count("1. 호흡계통의 구조") == 1
        assert l1_sections.count("2. 호흡의 조절") == 1
