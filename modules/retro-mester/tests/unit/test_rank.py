"""Unit tests for ranking / recommendations (T024).

RED -> GREEN: written before implementation.

Tests cover:
- rank_changes: top 3-5 covered, uncovered_ratio, quadrant mapping
- <3 gaps: all covered, no padding
- uncovered_ratio == 0.0 when all gaps are covered
"""

from __future__ import annotations

import math

from paideia_shared.schemas import (
    ChangeRecommendation,
    RetroMesterConfig,
    UnitGap,
)
from retro_mester.prioritize.rank import rank_changes

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_config(effort_ratings: dict[str, str] | None = None) -> RetroMesterConfig:
    return RetroMesterConfig(
        semester="2026-1",
        course_slug="anatomy",
        group_roster={"2026000001": "학령기"},
        unit_importance={},
        effort_ratings=effort_ratings or {},
    )


def _make_gap(
    chapter: str = "8장",
    segment: str = "학령기",
    n_below: int = 5,
    weight: float = 2.0,
    unit_importance: str = "중",
    pct_segment: float = 0.5,
    pct_cohort: float = 0.3,
    cause: str = "기초구멍",
    validity: str = "판정불가",
) -> UnitGap:
    """Build a minimal valid UnitGap for testing."""
    return UnitGap(
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        segment=segment,
        segment_mean_rate=0.4,
        n_below=n_below,
        pct_segment=pct_segment,
        pct_cohort=pct_cohort,
        is_structural=False,
        cohort_failing_item_types=[],
        cause=cause,
        cause_signals={"hard_share": 0.2, "item_mean_correct_rate": 0.4, "segment_mean_rate": 0.4},
        validity=validity,
        unit_importance=unit_importance,
        weight=weight,
        impact_score=n_below * weight,
        evidence_n=10,
    )


# ===========================================================================
# Tests for rank_changes
# ===========================================================================


class TestRankChanges:
    """Tests for retro_mester.prioritize.rank.rank_changes."""

    def test_returns_change_recommendation_instances(self) -> None:
        """rank_changes returns (list[ChangeRecommendation], float)."""
        gaps = [_make_gap()]
        config = _make_config()
        recs, ratio = rank_changes(gaps, config)

        assert isinstance(recs, list)
        assert all(isinstance(r, ChangeRecommendation) for r in recs)
        assert isinstance(ratio, float)

    def test_single_gap_is_covered(self) -> None:
        """With 1 gap (<3), it is covered with rank=1."""
        gaps = [_make_gap()]
        config = _make_config()
        recs, ratio = rank_changes(gaps, config)

        assert len(recs) == 1
        assert recs[0].is_covered is True
        assert recs[0].rank == 1

    def test_two_gaps_both_covered(self) -> None:
        """With 2 gaps (<3), both are covered (no padding)."""
        gaps = [
            _make_gap(chapter="8장", n_below=5),
            _make_gap(chapter="9장", n_below=3),
        ]
        config = _make_config()
        recs, ratio = rank_changes(gaps, config)

        assert len(recs) == 2
        assert all(r.is_covered for r in recs)
        assert {r.rank for r in recs} == {1, 2}

    def test_top_five_covered(self) -> None:
        """With exactly 5 gaps, all 5 are covered (ranks 1-5)."""
        gaps = [
            _make_gap(chapter=f"{i}장", n_below=10 - i)
            for i in range(1, 6)
        ]
        config = _make_config()
        recs, ratio = rank_changes(gaps, config)

        covered = [r for r in recs if r.is_covered]
        uncovered = [r for r in recs if not r.is_covered]
        assert len(covered) == 5
        assert len(uncovered) == 0
        assert {r.rank for r in covered} == {1, 2, 3, 4, 5}

    def test_more_than_five_caps_at_five(self) -> None:
        """With 7 gaps, only top 5 (by impact_score) are covered."""
        gaps = [
            _make_gap(chapter=f"{i}장", n_below=i)
            for i in range(1, 8)
        ]
        config = _make_config()
        recs, ratio = rank_changes(gaps, config)

        covered = [r for r in recs if r.is_covered]
        uncovered = [r for r in recs if not r.is_covered]
        assert len(covered) == 5
        assert len(uncovered) == 2
        assert {r.rank for r in covered} == {1, 2, 3, 4, 5}
        assert all(r.rank is None for r in uncovered)

    def test_uncovered_ratio_zero_when_all_covered(self) -> None:
        """uncovered_ratio == 0.0 when all gaps are covered."""
        gaps = [_make_gap(chapter=f"{i}장", n_below=5) for i in range(1, 4)]
        config = _make_config()
        _, ratio = rank_changes(gaps, config)

        assert math.isclose(ratio, 0.0, abs_tol=1e-9)

    def test_uncovered_ratio_correct(self) -> None:
        """uncovered_ratio = uncovered_count / total_gaps."""
        # 7 gaps → 5 covered, 2 uncovered → ratio = 2/7
        gaps = [
            _make_gap(chapter=f"{i}장", n_below=i)
            for i in range(1, 8)
        ]
        config = _make_config()
        _, ratio = rank_changes(gaps, config)

        assert math.isclose(ratio, 2 / 7, rel_tol=1e-9)

    def test_sorted_by_impact_score_desc(self) -> None:
        """Covered recs are assigned ranks by impact_score descending."""
        gaps = [
            _make_gap(chapter="1장", n_below=2, weight=2.0),  # impact=4
            _make_gap(chapter="2장", n_below=5, weight=2.0),  # impact=10
            _make_gap(chapter="3장", n_below=3, weight=2.0),  # impact=6
        ]
        config = _make_config()
        recs, _ = rank_changes(gaps, config)

        # Sort recs by rank for inspection
        covered = sorted([r for r in recs if r.is_covered], key=lambda r: r.rank)
        assert covered[0].chapter == "2장"  # impact=10, rank=1
        assert covered[1].chapter == "3장"  # impact=6, rank=2
        assert covered[2].chapter == "1장"  # impact=4, rank=3

    def test_no_padding_when_fewer_than_three(self) -> None:
        """With 1 or 2 gaps, no extra entries added (no padding)."""
        gaps = [_make_gap(chapter="8장", n_below=5)]
        config = _make_config()
        recs, _ = rank_changes(gaps, config)

        assert len(recs) == 1  # exactly 1, not padded to 3

    def test_quadrant_high_impact_low_effort(self) -> None:
        """High impact + low effort (하/중) → 빠른승리."""
        # Make 2 gaps so we have a median to work with
        gaps = [
            _make_gap(chapter="8장", n_below=10, weight=3.0),  # impact=30 (high)
            _make_gap(chapter="9장", n_below=1, weight=1.0),   # impact=1 (low)
        ]
        # 중 effort = not 상 → low effort
        config = _make_config(effort_ratings={"8장": "중"})
        recs, _ = rank_changes(gaps, config)

        high_impact_rec = next(r for r in recs if r.chapter == "8장")
        assert high_impact_rec.priority_quadrant == "빠른승리"

    def test_quadrant_high_impact_high_effort(self) -> None:
        """High impact + high effort (상) → 큰베팅."""
        gaps = [
            _make_gap(chapter="8장", n_below=10, weight=3.0),  # impact=30 (high)
            _make_gap(chapter="9장", n_below=1, weight=1.0),   # impact=1 (low)
        ]
        config = _make_config(effort_ratings={"8장": "상"})
        recs, _ = rank_changes(gaps, config)

        high_impact_rec = next(r for r in recs if r.chapter == "8장")
        assert high_impact_rec.priority_quadrant == "큰베팅"

    def test_quadrant_low_impact_low_effort(self) -> None:
        """Low impact + low effort → 낮은우선."""
        gaps = [
            _make_gap(chapter="8장", n_below=10, weight=3.0),  # impact=30 (high)
            _make_gap(chapter="9장", n_below=1, weight=1.0),   # impact=1 (low)
        ]
        config = _make_config(effort_ratings={"9장": "하"})
        recs, _ = rank_changes(gaps, config)

        low_impact_rec = next(r for r in recs if r.chapter == "9장")
        assert low_impact_rec.priority_quadrant == "낮은우선"

    def test_quadrant_low_impact_high_effort(self) -> None:
        """Low impact + high effort → 보류."""
        gaps = [
            _make_gap(chapter="8장", n_below=10, weight=3.0),  # impact=30 (high)
            _make_gap(chapter="9장", n_below=1, weight=1.0),   # impact=1 (low)
        ]
        config = _make_config(effort_ratings={"9장": "상"})
        recs, _ = rank_changes(gaps, config)

        low_impact_rec = next(r for r in recs if r.chapter == "9장")
        assert low_impact_rec.priority_quadrant == "보류"

    def test_fields_copied_from_gap(self) -> None:
        """ChangeRecommendation mirrors gap fields correctly."""
        gap = _make_gap(
            chapter="8장",
            segment="만학도",
            n_below=5,
            weight=3.0,
            unit_importance="상",
            pct_segment=0.5,
            pct_cohort=0.25,
            cause="기초구멍",
            validity="판정불가",
        )
        config = _make_config()
        recs, _ = rank_changes([gap], config)

        rec = recs[0]
        assert rec.chapter == "8장"
        assert rec.segment == "만학도"
        assert rec.covered_n == 5
        assert rec.unit_importance == "상"
        assert math.isclose(rec.weight, 3.0, rel_tol=1e-9)
        assert math.isclose(rec.covered_pct_segment, 0.5, rel_tol=1e-9)
        assert math.isclose(rec.covered_pct_cohort, 0.25, rel_tol=1e-9)
        assert rec.cause_hypothesis == "기초구멍"
        assert rec.validity == "판정불가"

    def test_effort_fallback_to_중(self) -> None:
        """Effort defaults to '중' when chapter not in effort_ratings."""
        gaps = [_make_gap(chapter="8장")]
        config = _make_config(effort_ratings={})
        recs, _ = rank_changes(gaps, config)

        assert recs[0].effort_level == "중"

    def test_effort_segment_keyed_lookup(self) -> None:
        """effort_ratings key '{chapter}|{segment}' is checked as fallback."""
        gaps = [_make_gap(chapter="8장", segment="만학도")]
        config = _make_config(effort_ratings={"8장|만학도": "상"})
        recs, _ = rank_changes(gaps, config)

        assert recs[0].effort_level == "상"

    def test_empty_gaps_returns_empty_list(self) -> None:
        """Empty gaps list → empty recs, uncovered_ratio=0.0."""
        config = _make_config()
        recs, ratio = rank_changes([], config)

        assert recs == []
        assert math.isclose(ratio, 0.0, abs_tol=1e-9)
