"""T041 — Unit tests for forward/next_items.py: propose_next_items.

RED phase: written before implementation.

Verifies:
- Structural gaps → chapter self-understanding proposal (likert).
- '생물 최종학습 시기' single_select proposal always emitted.
- Dedup by missing_signal (no duplicates even with multiple structural chapters).
- Non-structural gaps do NOT generate chapter proposals.
- write_next_items_md produces a markdown table.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import CombinedAnalysisRow, RetroMesterConfig, UnitGap

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_CHAPTER_A = "1장 해부학 서론"
_CHAPTER_B = "2장 세포와 조직"

_AXES = [
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
]


def _row(
    student_id: str,
    chapter_rates: dict[str, float],
    interest_rate: float | None = None,
    aversion_rate: float | None = None,
) -> CombinedAnalysisRow:
    d: dict = {
        "student_id": student_id,
        "name_kr": None,
        "on_roster": True,
        "section": None,
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "cluster_id": None,
        "cluster_label": None,
        "cluster_distance": None,
        "exam_taken": True,
        "total_score": 60.0,
        "score_percent": 60.0,
        "section_percentile": 50.0,
        "cohort_percentile": 50.0,
        "z_score": 0.0,
        "chapter_correct_rates": chapter_rates,
        "source_correct_rates": {},
        "difficulty_correct_rates": {},
        "expected_difficulty_correct_rates": {},
        "item_type_correct_rates": {},
        "interest_chapters_correct_rate": interest_rate,
        "aversion_chapters_correct_rate": aversion_rate,
        "prior_readiness_q5": None,
        "prior_readiness_q6": None,
        "time_pattern_q21": None,
        "time_pattern_q22": None,
        "time_pattern_q23": None,
        "interest_topics_q9": None,
        "interest_topics_q10": None,
        "interest_topics_q11": None,
        "categorical_intent_q12": None,
        "categorical_intent_q13": None,
        "진단응답": False,
        "시험응시": True,
        "needs_map_schema_version": "0.1.1",
        "immersio_phase2_schema_version": "0.1.0",
    }
    for axis in _AXES:
        d[f"{axis}_raw"] = None
        d[f"{axis}_z"] = None
        d[f"{axis}_missing"] = True
    return CombinedAnalysisRow(**d)


def _gap(
    chapter: str = _CHAPTER_A,
    segment: str = "학령기",
    is_structural: bool = True,
) -> UnitGap:
    return UnitGap(
        semester=_SEMESTER,
        course_slug=_COURSE,
        chapter=chapter,
        segment=segment,
        segment_mean_rate=0.45,
        n_below=3,
        pct_segment=0.75,
        pct_cohort=0.4,
        is_structural=is_structural,
        cohort_failing_item_types=[],
        cause="내용난이도",
        cause_signals={},
        validity="판정불가",
        unit_importance="상",
        weight=3.0,
        impact_score=9.0,
        evidence_n=4,
    )


def _config(roster: dict[str, str] | None = None) -> RetroMesterConfig:
    return RetroMesterConfig(
        semester=_SEMESTER,
        course_slug=_COURSE,
        group_roster=roster or {"2026000001": "학령기"},
        unit_importance={_CHAPTER_A: "상", _CHAPTER_B: "중"},
        gap_threshold=0.6,
        baseline_segment="만학도",
        low_discrimination_threshold=0.2,
        cognitive_cliff_drop=0.15,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProposeNextItems:
    """T041: propose_next_items rule-based proposals."""

    def test_structural_gap_emits_chapter_proposal(self) -> None:
        """A structural gap chapter generates a likert chapter self-understanding proposal."""
        from retro_mester.forward.next_items import propose_next_items

        rows = [_row("2026000001", {_CHAPTER_A: 0.4})]
        gaps = [_gap(_CHAPTER_A, "학령기", is_structural=True)]
        config = _config()

        proposals = propose_next_items(gaps, rows, config)

        chapter_proposals = [
            p for p in proposals
            if _CHAPTER_A in p.target_unit_or_axis and p.proposed_kind == "likert"
        ]
        assert len(chapter_proposals) >= 1

    def test_always_emits_생물_최종학습_시기(self) -> None:
        """'생물 최종학습 시기' single_select proposal is always present."""
        from retro_mester.forward.next_items import propose_next_items

        rows = [_row("2026000001", {_CHAPTER_A: 0.8})]
        gaps: list[UnitGap] = []  # no gaps at all
        config = _config()

        proposals = propose_next_items(gaps, rows, config)

        bio_proposals = [
            p for p in proposals
            if p.missing_signal == "생물 최종학습 시기"
        ]
        assert len(bio_proposals) == 1
        assert bio_proposals[0].proposed_kind == "single_select"

    def test_non_structural_gap_no_chapter_proposal(self) -> None:
        """A non-structural gap does NOT generate a chapter self-understanding proposal."""
        from retro_mester.forward.next_items import propose_next_items

        rows = [_row("2026000001", {_CHAPTER_B: 0.4})]
        gaps = [_gap(_CHAPTER_B, "학령기", is_structural=False)]
        config = _config()

        proposals = propose_next_items(gaps, rows, config)

        chapter_proposals = [
            p for p in proposals
            if _CHAPTER_B in p.target_unit_or_axis and p.proposed_kind == "likert"
        ]
        assert len(chapter_proposals) == 0

    def test_dedup_same_chapter_multiple_segments(self) -> None:
        """Two structural gaps on the same chapter (different segments) → one proposal."""
        from retro_mester.forward.next_items import propose_next_items

        rows = [
            _row("2026000001", {_CHAPTER_A: 0.4}),
            _row("2026000002", {_CHAPTER_A: 0.3}),
        ]
        # Same chapter, two segments, both structural
        gaps = [
            _gap(_CHAPTER_A, "학령기", is_structural=True),
            _gap(_CHAPTER_A, "만학도", is_structural=True),
        ]
        config = _config({"2026000001": "학령기", "2026000002": "만학도"})

        proposals = propose_next_items(gaps, rows, config)

        # Deduplicated by missing_signal: only one chapter-A proposal
        missing_signals = [p.missing_signal for p in proposals]
        chapter_a_signals = [s for s in missing_signals if _CHAPTER_A in s]
        assert len(chapter_a_signals) == 1

    def test_semester_and_course_on_proposals(self) -> None:
        """All proposals carry semester and course_slug from config."""
        from retro_mester.forward.next_items import propose_next_items

        rows = [_row("2026000001", {_CHAPTER_A: 0.4})]
        gaps = [_gap(_CHAPTER_A, "학령기", is_structural=True)]
        config = _config()

        proposals = propose_next_items(gaps, rows, config)

        for p in proposals:
            assert p.semester == _SEMESTER
            assert p.course_slug == _COURSE

    def test_multiple_structural_chapters_no_duplication(self) -> None:
        """Multiple structural gap chapters produce one proposal each, no duplicates."""
        from retro_mester.forward.next_items import propose_next_items

        rows = [
            _row("2026000001", {_CHAPTER_A: 0.3, _CHAPTER_B: 0.25}),
        ]
        gaps = [
            _gap(_CHAPTER_A, "학령기", is_structural=True),
            _gap(_CHAPTER_B, "학령기", is_structural=True),
        ]
        config = _config()

        proposals = propose_next_items(gaps, rows, config)

        # One for CHAPTER_A, one for CHAPTER_B, one for 생물 최종학습 시기
        missing_signals = [p.missing_signal for p in proposals]
        assert len(missing_signals) == len(set(missing_signals)), (
            "Duplicate missing_signal values found"
        )

    def test_no_gaps_returns_bio_proposal_only(self) -> None:
        """With no gaps, only the '생물 최종학습 시기' proposal is emitted."""
        from retro_mester.forward.next_items import propose_next_items

        rows = [_row("2026000001", {_CHAPTER_A: 0.9})]
        gaps: list[UnitGap] = []
        config = _config()

        proposals = propose_next_items(gaps, rows, config)

        assert len(proposals) == 1
        assert proposals[0].missing_signal == "생물 최종학습 시기"


class TestWriteNextItemsMd:
    """T041: write_next_items_md produces a valid Markdown table."""

    def test_produces_markdown_table(self, tmp_path: Path) -> None:
        """Output file contains a pipe-delimited Markdown table."""
        from retro_mester.forward.next_items import propose_next_items, write_next_items_md

        rows = [_row("2026000001", {_CHAPTER_A: 0.4})]
        gaps = [_gap(_CHAPTER_A, "학령기", is_structural=True)]
        config = _config()
        proposals = propose_next_items(gaps, rows, config)

        out = tmp_path / "차년도진단문항제안.md"
        write_next_items_md(out, proposals)

        text = out.read_text(encoding="utf-8")
        assert "|" in text, "Expected pipe-delimited table"

    def test_contains_all_proposals(self, tmp_path: Path) -> None:
        """All proposals appear as rows in the table."""
        from retro_mester.forward.next_items import propose_next_items, write_next_items_md

        rows = [_row("2026000001", {_CHAPTER_A: 0.4})]
        gaps = [_gap(_CHAPTER_A, "학령기", is_structural=True)]
        config = _config()
        proposals = propose_next_items(gaps, rows, config)

        out = tmp_path / "차년도진단문항제안.md"
        write_next_items_md(out, proposals)

        text = out.read_text(encoding="utf-8")
        for p in proposals:
            assert p.missing_signal in text
