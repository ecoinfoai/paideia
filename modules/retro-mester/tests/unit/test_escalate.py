"""Unit tests for structural escalation (T032, US2).

RED -> GREEN: written before implementation.

SC-004: When the baseline segment ALSO has a mean correct rate below
``gap_threshold`` for a chapter, ALL gaps for that chapter are
escalated to ``is_structural=True``.  Chapters where baseline segment
is at or above threshold are NOT escalated.
"""

from __future__ import annotations

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    RetroMesterConfig,
    UnitGap,
)

# ---------------------------------------------------------------------------
# Minimal factories (mirrors test_gaps_detect.py pattern)
# ---------------------------------------------------------------------------

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

_AXIS_MISSING = {f"{ax}_missing": True for ax in _AXES}
_AXIS_RAW = {f"{ax}_raw": None for ax in _AXES}
_AXIS_Z = {f"{ax}_z": None for ax in _AXES}


def _make_row(
    student_id: str,
    chapter_rates: dict[str, float],
) -> CombinedAnalysisRow:
    """Build a minimal valid CombinedAnalysisRow for testing."""
    base = {
        "student_id": student_id,
        "name_kr": None,
        "on_roster": True,
        "section": None,
        "semester": "2026-1",
        "course_slug": "anatomy",
        "exam_taken": True,
        "total_score": 70.0,
        "score_percent": 70.0,
        "section_percentile": 50.0,
        "cohort_percentile": 50.0,
        "z_score": 0.0,
        "chapter_correct_rates": chapter_rates,
        "source_correct_rates": {},
        "difficulty_correct_rates": {},
        "expected_difficulty_correct_rates": {},
        "item_type_correct_rates": {},
        "interest_chapters_correct_rate": None,
        "aversion_chapters_correct_rate": None,
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
        "cluster_id": None,
        "cluster_label": None,
        "cluster_distance": None,
    }
    base.update(_AXIS_MISSING)
    base.update(_AXIS_RAW)
    base.update(_AXIS_Z)
    return CombinedAnalysisRow(**base)


def _make_gap(
    chapter: str = "8장",
    segment: str = "학령기",
    n_below: int = 2,
    weight: float = 2.0,
    is_structural: bool = False,
) -> UnitGap:
    """Build a minimal valid UnitGap with provisional is_structural=False."""
    return UnitGap(
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        segment=segment,
        segment_mean_rate=0.4,
        n_below=n_below,
        pct_segment=0.5,
        pct_cohort=0.3,
        is_structural=is_structural,
        cohort_failing_item_types=[],
        cause="기초구멍",
        cause_signals={
            "hard_share": 0.2,
            "item_mean_correct_rate": 0.4,
            "segment_mean_rate": 0.4,
        },
        validity="판정불가",
        unit_importance="중",
        weight=weight,
        impact_score=n_below * weight,
        evidence_n=4,
    )


def _make_config(
    roster: dict[str, str],
    gap_threshold: float = 0.6,
    baseline_segment: str = "만학도",
) -> RetroMesterConfig:
    """Build a minimal valid RetroMesterConfig for testing."""
    return RetroMesterConfig(
        semester="2026-1",
        course_slug="anatomy",
        group_roster=roster,
        unit_importance={},
        gap_threshold=gap_threshold,
        baseline_segment=baseline_segment,
        effort_ratings={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEscalateStructural:
    """Tests for retro_mester.gaps.escalate.escalate_structural."""

    def test_baseline_also_below_threshold_sets_structural_true(self) -> None:
        """SC-004: both segments below threshold → all chapter gaps escalated."""
        from retro_mester.gaps.escalate import escalate_structural

        # 학령기 below (gap), 만학도 (baseline) also below (structural trigger)
        rows = [
            _make_row("2026000001", {"8장": 0.4}),  # 학령기, below
            _make_row("2026000002", {"8장": 0.3}),  # 만학도, below
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")

        gaps = [_make_gap(chapter="8장", segment="학령기")]
        result = escalate_structural(gaps, rows, config)

        assert len(result) == 1
        assert result[0].is_structural is True

    def test_baseline_above_threshold_leaves_structural_false(self) -> None:
        """Baseline at or above threshold → is_structural stays False."""
        from retro_mester.gaps.escalate import escalate_structural

        # 학령기 below (gap emitted), 만학도 (baseline) above threshold
        rows = [
            _make_row("2026000001", {"8장": 0.4}),  # 학령기, below
            _make_row("2026000002", {"8장": 0.8}),  # 만학도, above threshold
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")

        gaps = [_make_gap(chapter="8장", segment="학령기")]
        result = escalate_structural(gaps, rows, config)

        assert len(result) == 1
        assert result[0].is_structural is False

    def test_baseline_at_threshold_leaves_structural_false(self) -> None:
        """Baseline exactly at threshold (== gap_threshold) → not escalated (strict <)."""
        from retro_mester.gaps.escalate import escalate_structural

        rows = [
            _make_row("2026000001", {"8장": 0.4}),  # 학령기, below
            _make_row("2026000002", {"8장": 0.6}),  # 만학도, AT threshold
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, gap_threshold=0.6, baseline_segment="만학도")

        gaps = [_make_gap(chapter="8장", segment="학령기")]
        result = escalate_structural(gaps, rows, config)

        assert result[0].is_structural is False

    def test_multiple_chapters_independent_escalation(self) -> None:
        """Escalation is per-chapter: one chapter escalated, another not."""
        from retro_mester.gaps.escalate import escalate_structural

        rows = [
            _make_row("2026000001", {"8장": 0.4, "9장": 0.4}),  # 학령기
            _make_row("2026000002", {"8장": 0.3, "9장": 0.8}),  # 만학도
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")

        # Gap on both chapters for 학령기
        gaps = [
            _make_gap(chapter="8장", segment="학령기"),
            _make_gap(chapter="9장", segment="학령기"),
        ]
        result = escalate_structural(gaps, rows, config)

        by_chapter = {g.chapter: g for g in result}
        # 8장: 만학도 rate 0.3 < 0.6 → structural
        assert by_chapter["8장"].is_structural is True
        # 9장: 만학도 rate 0.8 >= 0.6 → not structural
        assert by_chapter["9장"].is_structural is False

    def test_all_gaps_in_structural_chapter_escalated(self) -> None:
        """All gaps for a structural chapter are escalated (both segments)."""
        from retro_mester.gaps.escalate import escalate_structural

        rows = [
            _make_row("2026000001", {"8장": 0.4}),  # 학령기, below
            _make_row("2026000002", {"8장": 0.3}),  # 만학도, below (baseline also low)
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")

        # Both segments have a gap for 8장
        gaps = [
            _make_gap(chapter="8장", segment="학령기"),
            _make_gap(chapter="8장", segment="만학도"),
        ]
        result = escalate_structural(gaps, rows, config)

        assert all(g.is_structural is True for g in result)

    def test_empty_gaps_returns_empty(self) -> None:
        """Empty gap list → empty result."""
        from retro_mester.gaps.escalate import escalate_structural

        config = _make_config(roster={})
        result = escalate_structural([], [], config)
        assert result == []

    def test_no_baseline_students_leaves_structural_false(self) -> None:
        """No baseline-segment students for a chapter → cannot escalate → False."""
        from retro_mester.gaps.escalate import escalate_structural

        rows = [
            _make_row("2026000001", {"8장": 0.4}),  # 학령기, below
            # No 만학도 (baseline) students for this chapter
        ]
        roster = {"2026000001": "학령기"}
        config = _make_config(roster=roster, baseline_segment="만학도")

        gaps = [_make_gap(chapter="8장", segment="학령기")]
        result = escalate_structural(gaps, rows, config)

        assert result[0].is_structural is False

    def test_returns_unit_gap_instances(self) -> None:
        """escalate_structural returns a list of UnitGap instances."""
        from retro_mester.gaps.escalate import escalate_structural

        rows = [_make_row("2026000001", {"8장": 0.4})]
        roster = {"2026000001": "학령기"}
        config = _make_config(roster=roster)

        gaps = [_make_gap(chapter="8장")]
        result = escalate_structural(gaps, rows, config)

        assert all(isinstance(g, UnitGap) for g in result)

    def test_frozen_gaps_rebuilt_not_mutated(self) -> None:
        """Original UnitGap objects are unchanged; new instances are returned."""
        from retro_mester.gaps.escalate import escalate_structural

        rows = [
            _make_row("2026000001", {"8장": 0.4}),
            _make_row("2026000002", {"8장": 0.3}),
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")

        original_gap = _make_gap(chapter="8장", segment="학령기")
        result = escalate_structural([original_gap], rows, config)

        # Original must be unchanged (frozen model)
        assert original_gap.is_structural is False
        # Returned must be escalated
        assert result[0].is_structural is True
        # They are different objects
        assert result[0] is not original_gap
