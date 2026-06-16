"""Unit tests for maieutica.plan.slots.assign_subsections — T010 (contract A1–A7).

TDD: failing tests written BEFORE implementation (RED → GREEN).

Covers the binding contract ``contracts/slot_assignment.md``:
- A1 length-proportional (Hamilton/largest-remainder): longer subsection ≥ shorter.
- A2 cap ≤3 per subsection.
- A3/A4 overflow + capacity = min(N, 3·len(chunks)); surplus dropped here.
- A5 contiguous intra_ordinal 1..k within each subsection.
- A6 determinism under shuffled chunk input order.
- A7 spread: ≥2 subsections, N≥2 → assignment touches ≥2 subsections.
"""

from __future__ import annotations

from maieutica.plan.slots import Slot, assign_subsections
from paideia_shared.schemas import TextbookChunk


def _slots(n: int) -> list[Slot]:
    """Build *n* quiz slots with deterministic ids (mirrors plan_slots output)."""
    return [
        Slot(
            slot_id=f"quiz-3-{ordinal:03d}",
            kind="quiz",
            week=3,
            chapter_no=8,
            ordinal=ordinal,
        )
        for ordinal in range(1, n + 1)
    ]


def _chunk(chunk_id: str, *, chars: int, line_start: int, section: str) -> TextbookChunk:
    """Build a TextbookChunk whose body text has exactly *chars* characters."""
    return TextbookChunk(
        semester="2026-1",
        course_slug="anatomy",
        chunk_id=chunk_id,
        chapter_no=8,
        chapter="8장 호흡계통",
        section=section,
        source_file="8장 호흡계통.txt",
        line_start=line_start,
        line_end=line_start + 10,
        text="x" * chars,
        removed_spans=[],
    )


class TestAssignSubsections:
    def test_a4_capacity_three_chunks_fifteen_slots(self) -> None:
        """3 chunks + 15 slots → exactly 9 assigned, allocation [3,3,3]."""
        chunks = [
            _chunk("c1", chars=3000, line_start=10, section="1. A"),
            _chunk("c2", chars=2000, line_start=20, section="2. B"),
            _chunk("c3", chars=1000, line_start=30, section="3. C"),
        ]
        out = assign_subsections(_slots(15), chunks)

        assert len(out) == 9
        counts = {c.chunk_id: 0 for c in chunks}
        for s in out:
            counts[s.subsection_chunk_id] += 1
        assert sorted(counts.values(), reverse=True) == [3, 3, 3]

    def test_five_chunks_fifteen_slots_all_three(self) -> None:
        """5 chunks (3000/2000/1500/800/700), N=15 → [3,3,3,3,3]."""
        chunks = [
            _chunk("c1", chars=3000, line_start=10, section="1. A"),
            _chunk("c2", chars=2000, line_start=20, section="2. B"),
            _chunk("c3", chars=1500, line_start=30, section="3. C"),
            _chunk("c4", chars=800, line_start=40, section="4. D"),
            _chunk("c5", chars=700, line_start=50, section="5. E"),
        ]
        out = assign_subsections(_slots(15), chunks)

        assert len(out) == 15
        counts = {c.chunk_id: 0 for c in chunks}
        for s in out:
            counts[s.subsection_chunk_id] += 1
        assert sorted(counts.values(), reverse=True) == [3, 3, 3, 3, 3]

    def test_a2_cap_never_exceeded(self) -> None:
        """No subsection ever receives more than 3 slots."""
        chunks = [
            _chunk("c1", chars=9000, line_start=10, section="1. A"),
            _chunk("c2", chars=100, line_start=20, section="2. B"),
            _chunk("c3", chars=100, line_start=30, section="3. C"),
        ]
        out = assign_subsections(_slots(9), chunks)
        counts: dict[str, int] = {}
        for s in out:
            counts[s.subsection_chunk_id] = counts.get(s.subsection_chunk_id, 0) + 1
        assert all(v <= 3 for v in counts.values())

    def test_a1_length_proportional_longer_gets_at_least(self) -> None:
        """A longer subsection gets ≥ a shorter subsection's count (under cap)."""
        chunks = [
            _chunk("big", chars=5000, line_start=10, section="1. A"),
            _chunk("mid", chars=2000, line_start=20, section="2. B"),
            _chunk("small", chars=500, line_start=30, section="3. C"),
        ]
        # N below cap-bound (3*3=9) so proportionality (not the cap) governs.
        out = assign_subsections(_slots(6), chunks)
        counts = {c.chunk_id: 0 for c in chunks}
        for s in out:
            counts[s.subsection_chunk_id] += 1
        assert counts["big"] >= counts["mid"] >= counts["small"]
        assert sum(counts.values()) == 6

    def test_a5_intra_ordinal_contiguous(self) -> None:
        """Slots sharing a subsection have contiguous intra_ordinal 1..k."""
        chunks = [
            _chunk("c1", chars=3000, line_start=10, section="1. A"),
            _chunk("c2", chars=2000, line_start=20, section="2. B"),
            _chunk("c3", chars=1000, line_start=30, section="3. C"),
        ]
        out = assign_subsections(_slots(15), chunks)
        by_sub: dict[str, list[int]] = {}
        for s in out:
            by_sub.setdefault(s.subsection_chunk_id, []).append(s.intra_ordinal)
        for chunk_id, ordinals in by_sub.items():
            assert sorted(ordinals) == list(range(1, len(ordinals) + 1)), chunk_id

    def test_a5_subsection_fields_populated(self) -> None:
        """Every returned slot has chunk_id + section + intra_ordinal set."""
        chunks = [
            _chunk("c1", chars=3000, line_start=10, section="1. A"),
            _chunk("c2", chars=2000, line_start=20, section="2. B"),
        ]
        out = assign_subsections(_slots(4), chunks)
        for s in out:
            assert s.subsection_chunk_id != ""
            assert s.subsection_section is not None
            assert s.intra_ordinal >= 1

    def test_a6_determinism_under_shuffle(self) -> None:
        """Shuffled chunk input order yields an identical assignment (A6)."""
        ordered = [
            _chunk("c1", chars=3000, line_start=10, section="1. A"),
            _chunk("c2", chars=2000, line_start=20, section="2. B"),
            _chunk("c3", chars=1500, line_start=30, section="3. C"),
            _chunk("c4", chars=800, line_start=40, section="4. D"),
        ]
        shuffled = [ordered[2], ordered[0], ordered[3], ordered[1]]

        def fingerprint(out: list[Slot]) -> list[tuple[str, str, int]]:
            return [(s.slot_id, s.subsection_chunk_id, s.intra_ordinal) for s in out]

        a = assign_subsections(_slots(10), ordered)
        b = assign_subsections(_slots(10), shuffled)
        assert fingerprint(a) == fingerprint(b)
        # Re-run identical input → byte-identical.
        c = assign_subsections(_slots(10), ordered)
        assert fingerprint(a) == fingerprint(c)

    def test_a6_tie_break_line_start_then_chunk_id(self) -> None:
        """Equal char counts break by line_start asc, then chunk_id asc."""
        # All equal chars → sort governed purely by line_start then chunk_id.
        chunks = [
            _chunk("zzz", chars=1000, line_start=50, section="3. C"),
            _chunk("aaa", chars=1000, line_start=10, section="1. A"),
            _chunk("mmm", chars=1000, line_start=10, section="2. B"),
        ]
        out = assign_subsections(_slots(3), chunks)
        # First slot (ordinal 1) belongs to the sort-first subsection:
        # line_start 10 ties between "aaa" and "mmm" → chunk_id "aaa" wins.
        first = next(s for s in out if s.intra_ordinal == 1 and s.slot_id.endswith("001"))
        assert first.subsection_chunk_id == "aaa"

    def test_a7_spread_at_least_two_subsections(self) -> None:
        """≥2 subsections, N≥2 → assignment touches ≥2 distinct subsections."""
        chunks = [
            _chunk("c1", chars=9000, line_start=10, section="1. A"),
            _chunk("c2", chars=100, line_start=20, section="2. B"),
        ]
        out = assign_subsections(_slots(5), chunks)
        distinct = {s.subsection_chunk_id for s in out}
        assert len(distinct) >= 2

    def test_capacity_bound_all_assigned_when_under_cap(self) -> None:
        """N < 3·len(chunks) → all N slots assigned (no drop)."""
        chunks = [
            _chunk("c1", chars=3000, line_start=10, section="1. A"),
            _chunk("c2", chars=2000, line_start=20, section="2. B"),
            _chunk("c3", chars=1000, line_start=30, section="3. C"),
        ]
        out = assign_subsections(_slots(5), chunks)
        assert len(out) == 5

    def test_remainder_pool_spreads_not_concentrated(self) -> None:
        """pool>1 with distinct fractions, none capping → +1 each round (Hamilton).

        Char counts 9/8/3 (total 20), capacity 2 → ideals [0.9, 0.8, 0.3],
        floors [0,0,0], pool 2. Standard largest-remainder gives the two extra
        units to the two LARGEST distinct fractions → [1,1,0], NOT [2,0,0]
        (which a single-winner loop would produce, undermining A7 spread).
        """
        chunks = [
            _chunk("big", chars=9, line_start=10, section="1. A"),
            _chunk("mid", chars=8, line_start=20, section="2. B"),
            _chunk("small", chars=3, line_start=30, section="3. C"),
        ]
        out = assign_subsections(_slots(2), chunks)
        counts = {"big": 0, "mid": 0, "small": 0}
        for s in out:
            counts[s.subsection_chunk_id] += 1
        assert counts == {"big": 1, "mid": 1, "small": 0}
