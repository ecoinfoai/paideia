"""Unit tests for maieutica.silver.evidence_index — T022.

TDD: failing tests written BEFORE implementation (RED → GREEN).

Covers:
- A term present in the chapter → MaieuticaTextbookEvidence with chunk_id,
  found_text, and char offsets that index the ORIGINAL file
  (original_text[char_start:char_end] == found_text).
- A term absent → status="미확인".
- OFFSET TRAP: a fixture where the cleaner removes EARLIER lines must still
  produce char_start anchored at the correct ORIGINAL position (a naive impl
  derived from cleaned text would be off by the removed bytes).
"""

from __future__ import annotations

from maieutica.silver.chunk import chunk_chapter
from paideia_shared.schemas import MaieuticaTextbookEvidence

# ---------------------------------------------------------------------------
# Fixture with substantial EARLIER noise that the cleaner strips.  Lines 1–4
# are noise (removed); the body sections start later.  This is the offset trap:
# offsets computed from cleaned text alone would be short by the removed bytes.
# ---------------------------------------------------------------------------

FIXTURE_LINES: list[str] = [
    "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y",  # 1 — removed
    "제8장 호흡계통",  # 2 — removed (running header)
    "C H A P T E R  8",  # 3 — removed (spaced header)
    "200",  # 4 — removed (page number)
    "1. 호흡기의 구조",  # 5 — section heading (kept)
    "코는 후각과 공기 가습을 담당한다.",  # 6 — body (kept)
    "폐포에서 산소와 이산화탄소가 교환된다.",  # 7 — body (kept)
    "",  # 8 — blank
    "연습문제",  # 9 — exercise block (removed to EOF)
    "1. 코의 기능을 기술하시오.",  # 10
]

ORIGINAL_TEXT: str = "\n".join(FIXTURE_LINES)


def _chunks():
    return chunk_chapter(
        lines=FIXTURE_LINES,
        chapter_no=8,
        chapter="8장 호흡계통",
        semester="2026-1",
        course_slug="anatomy",
        source_file="8장 호흡계통.txt",
    )


class TestEvidenceIndex:
    def test_term_found_returns_confirmed_evidence(self) -> None:
        from maieutica.silver.evidence_index import EvidenceIndex

        idx = EvidenceIndex.from_chapter(
            lines=FIXTURE_LINES,
            chunks=_chunks(),
            source_file="8장 호흡계통.txt",
        )
        ev = idx.lookup("폐포")
        assert isinstance(ev, MaieuticaTextbookEvidence)
        assert ev.status == "확인"
        assert ev.chunk_id
        assert ev.found_text == "폐포에서 산소와 이산화탄소가 교환된다."

    def test_char_offsets_index_original_file(self) -> None:
        """char_start/char_end slice the ORIGINAL text to exactly found_text."""
        from maieutica.silver.evidence_index import EvidenceIndex

        idx = EvidenceIndex.from_chapter(
            lines=FIXTURE_LINES,
            chunks=_chunks(),
            source_file="8장 호흡계통.txt",
        )
        ev = idx.lookup("코는 후각")
        assert ev.status == "확인"
        assert ev.char_start is not None and ev.char_end is not None
        assert ORIGINAL_TEXT[ev.char_start : ev.char_end] == ev.found_text

    def test_offset_trap_earlier_lines_removed(self) -> None:
        """The body line's char_start must point at its ORIGINAL position even
        though lines 1–4 were stripped by the cleaner (offset trap)."""
        from maieutica.silver.evidence_index import EvidenceIndex

        idx = EvidenceIndex.from_chapter(
            lines=FIXTURE_LINES,
            chunks=_chunks(),
            source_file="8장 호흡계통.txt",
        )
        target = "폐포에서 산소와 이산화탄소가 교환된다."
        ev = idx.lookup("폐포")
        assert ev.found_text == target
        # The TRUE original offset, independent of the cleaner.
        expected_start = ORIGINAL_TEXT.index(target)
        assert ev.char_start == expected_start
        assert ORIGINAL_TEXT[ev.char_start : ev.char_end] == target
        # Guard the trap: a cleaned-text offset would be smaller (removed bytes).
        cleaned_text = "\n".join(
            t for c in _chunks() for t in c.text.split("\n")
        )
        naive_offset = cleaned_text.index(target)
        assert ev.char_start != naive_offset

    def test_term_absent_returns_unconfirmed(self) -> None:
        from maieutica.silver.evidence_index import EvidenceIndex

        idx = EvidenceIndex.from_chapter(
            lines=FIXTURE_LINES,
            chunks=_chunks(),
            source_file="8장 호흡계통.txt",
        )
        ev = idx.lookup("미토콘드리아")
        assert ev.status == "미확인"
        assert ev.chunk_id is None
        assert ev.char_start is None
        assert ev.search_term == "미토콘드리아"

    def test_term_in_noise_region_only_returns_unconfirmed(self) -> None:
        """SC-007 boundary: a term present ONLY in stripped noise (outside every
        chunk's line range) → 미확인 via the chunk_id-None branch.

        '연습문제' genuinely appears in FIXTURE_LINES (the exercise block) but
        that line is removed by the cleaner, so no chunk covers it.  This is
        distinct from the absent-term path (term not in the file at all)."""
        from maieutica.silver.evidence_index import EvidenceIndex

        # Precondition: the term IS present in the original file (so this
        # exercises the noise-region branch, not the absent-term path).
        assert any("연습문제" in line for line in FIXTURE_LINES)

        idx = EvidenceIndex.from_chapter(
            lines=FIXTURE_LINES,
            chunks=_chunks(),
            source_file="8장 호흡계통.txt",
        )
        ev = idx.lookup("연습문제")
        assert ev.status == "미확인"
        assert ev.chunk_id is None
        assert ev.char_start is None
        assert ev.search_term == "연습문제"
