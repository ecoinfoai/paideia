"""T038 — Unit tests for forward/ledger.py: build_ledger.

RED phase: written before implementation.

Verifies:
- One ledger entry per COVERED recommendation.
- entry_id is deterministic (same inputs → same hash).
- baseline_value comes from gap's segment_mean_rate.
- target_value = min(gap_threshold + 0.1, 1.0).
- metric = "단원 정답률".
- measure_at = "차년도 기말".
- cluster_vocab carried from recommendation.
"""

from __future__ import annotations

import json

import pytest

from paideia_shared.schemas import (
    ChangeRecommendation,
    CombinedAnalysisRow,
    RetroMesterConfig,
    UnitGap,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_CHAPTER_A = "1장 해부학 서론"
_CHAPTER_B = "2장 세포와 조직"


def _make_gap(
    chapter: str = _CHAPTER_A,
    segment: str = "학령기",
    segment_mean_rate: float = 0.45,
    n_below: int = 3,
    is_structural: bool = False,
) -> UnitGap:
    """Build a minimal UnitGap."""
    return UnitGap(
        semester=_SEMESTER,
        course_slug=_COURSE,
        chapter=chapter,
        segment=segment,
        segment_mean_rate=segment_mean_rate,
        n_below=n_below,
        pct_segment=0.75,
        pct_cohort=0.4,
        is_structural=is_structural,
        cohort_failing_item_types=[],
        cause="내용난이도",
        cause_signals={},
        validity="판정불가",
        unit_importance="상",
        weight=3.0,
        impact_score=float(n_below * 3),
        evidence_n=4,
    )


def _make_rec(
    chapter: str = _CHAPTER_A,
    segment: str = "학령기",
    is_covered: bool = True,
    rank: int | None = 1,
    cluster_vocab: str | None = None,
    target_cognitive_level: str = "미상",
) -> ChangeRecommendation:
    """Build a minimal ChangeRecommendation."""
    return ChangeRecommendation(
        semester=_SEMESTER,
        course_slug=_COURSE,
        rank=rank,
        chapter=chapter,
        target_cognitive_level=target_cognitive_level,
        segment=segment,
        cause_hypothesis="내용난이도",
        covered_n=3,
        covered_pct_segment=0.75,
        covered_pct_cohort=0.4,
        unit_importance="상",
        weight=3.0,
        impact_score=9.0,
        effort_level="중",
        priority_quadrant="빠른승리",
        prescription_key="내용난이도/학령기",
        cluster_vocab=cluster_vocab,
        validity="판정불가",
        is_covered=is_covered,
    )


def _config() -> RetroMesterConfig:
    return RetroMesterConfig(
        semester=_SEMESTER,
        course_slug=_COURSE,
        group_roster={"2026000001": "학령기"},
        unit_importance={_CHAPTER_A: "상", _CHAPTER_B: "중"},
        gap_threshold=0.6,
        baseline_segment="만학도",
        low_discrimination_threshold=0.2,
        cognitive_cliff_drop=0.15,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildLedger:
    """T038: build_ledger produces one entry per covered recommendation."""

    def test_one_entry_per_covered_rec(self) -> None:
        """Exactly one ImprovementLedgerEntry per covered recommendation."""
        from retro_mester.forward.ledger import build_ledger

        covered_recs = [
            _make_rec(_CHAPTER_A, "학령기", is_covered=True, rank=1),
            _make_rec(_CHAPTER_B, "만학도", is_covered=True, rank=2),
        ]
        gaps = [
            _make_gap(_CHAPTER_A, "학령기", segment_mean_rate=0.45),
            _make_gap(_CHAPTER_B, "만학도", segment_mean_rate=0.50),
        ]
        config = _config()
        result = build_ledger(covered_recs, gaps, config, created_for_year="2027-1")

        assert len(result) == 2

    def test_metric_is_단원_정답률(self) -> None:
        """metric field is '단원 정답률' on every ledger entry."""
        from retro_mester.forward.ledger import build_ledger

        covered_recs = [_make_rec()]
        gaps = [_make_gap()]
        result = build_ledger(covered_recs, gaps, _config(), created_for_year="2027-1")

        assert all(e.metric == "단원 정답률" for e in result)

    def test_baseline_value_from_gap_segment_mean(self) -> None:
        """baseline_value equals the matching gap's segment_mean_rate."""
        from retro_mester.forward.ledger import build_ledger

        gap = _make_gap(_CHAPTER_A, "학령기", segment_mean_rate=0.42)
        rec = _make_rec(_CHAPTER_A, "학령기")
        result = build_ledger([rec], [gap], _config(), created_for_year="2027-1")

        assert len(result) == 1
        assert abs(result[0].baseline_value - 0.42) < 1e-9

    def test_target_value_uplift(self) -> None:
        """target_value = min(gap_threshold + 0.1, 1.0)."""
        from retro_mester.forward.ledger import build_ledger

        config = _config()
        # gap_threshold = 0.6, so target should be 0.7
        rec = _make_rec()
        gap = _make_gap()
        result = build_ledger([rec], [gap], config, created_for_year="2027-1")

        assert abs(result[0].target_value - 0.7) < 1e-9

    def test_target_value_clamped_at_1(self) -> None:
        """target_value is clamped at 1.0 when gap_threshold + 0.1 > 1.0."""
        from retro_mester.forward.ledger import build_ledger

        # Build a config with gap_threshold = 0.95 → uplift would be 1.05 → clamped to 1.0
        from paideia_shared.schemas import RetroMesterConfig

        config = RetroMesterConfig(
            semester=_SEMESTER,
            course_slug=_COURSE,
            group_roster={"2026000001": "학령기"},
            unit_importance={_CHAPTER_A: "상"},
            gap_threshold=0.95,
            baseline_segment="만학도",
            low_discrimination_threshold=0.2,
            cognitive_cliff_drop=0.15,
        )
        gap = _make_gap(_CHAPTER_A, "학령기", segment_mean_rate=0.92)
        rec = _make_rec()
        result = build_ledger([rec], [gap], config, created_for_year="2027-1")

        assert result[0].target_value == 1.0

    def test_measure_at_is_차년도_기말(self) -> None:
        """measure_at is always '차년도 기말'."""
        from retro_mester.forward.ledger import build_ledger

        result = build_ledger([_make_rec()], [_make_gap()], _config(), created_for_year="2027-1")
        assert result[0].measure_at == "차년도 기말"

    def test_entry_id_deterministic(self) -> None:
        """Same inputs produce the same entry_id across multiple calls."""
        from retro_mester.forward.ledger import build_ledger

        rec = _make_rec(_CHAPTER_A, "학령기", target_cognitive_level="미상")
        gap = _make_gap(_CHAPTER_A, "학령기")
        config = _config()

        r1 = build_ledger([rec], [gap], config, created_for_year="2027-1")
        r2 = build_ledger([rec], [gap], config, created_for_year="2027-1")

        assert r1[0].entry_id == r2[0].entry_id

    def test_entry_id_differs_for_different_inputs(self) -> None:
        """Different chapter/segment/cognitive_level combos yield different entry_ids."""
        from retro_mester.forward.ledger import build_ledger

        rec_a = _make_rec(_CHAPTER_A, "학령기", target_cognitive_level="미상")
        rec_b = _make_rec(_CHAPTER_B, "만학도", target_cognitive_level="미상")
        gap_a = _make_gap(_CHAPTER_A, "학령기")
        gap_b = _make_gap(_CHAPTER_B, "만학도")
        config = _config()

        r_a = build_ledger([rec_a], [gap_a], config, created_for_year="2027-1")
        r_b = build_ledger([rec_b], [gap_b], config, created_for_year="2027-1")

        assert r_a[0].entry_id != r_b[0].entry_id

    def test_cluster_vocab_carried_from_rec(self) -> None:
        """cluster_vocab is copied from the recommendation."""
        from retro_mester.forward.ledger import build_ledger

        rec = _make_rec(cluster_vocab="습관중심형")
        gap = _make_gap()
        result = build_ledger([rec], [gap], _config(), created_for_year="2027-1")

        assert result[0].cluster_vocab == "습관중심형"

    def test_created_for_year_set(self) -> None:
        """created_for_year is carried onto each entry."""
        from retro_mester.forward.ledger import build_ledger

        result = build_ledger([_make_rec()], [_make_gap()], _config(), created_for_year="2027-1")
        assert result[0].created_for_year == "2027-1"

    def test_empty_covered_recs_returns_empty(self) -> None:
        """build_ledger with no covered recs returns empty list."""
        from retro_mester.forward.ledger import build_ledger

        result = build_ledger([], [], _config(), created_for_year="2027-1")
        assert result == []

    def test_uncovered_rec_excluded(self) -> None:
        """Only covered (is_covered=True) recommendations generate ledger entries."""
        from retro_mester.forward.ledger import build_ledger

        covered = _make_rec(_CHAPTER_A, "학령기", is_covered=True, rank=1)
        uncovered = _make_rec(_CHAPTER_B, "만학도", is_covered=False, rank=None)
        gaps = [
            _make_gap(_CHAPTER_A, "학령기"),
            _make_gap(_CHAPTER_B, "만학도"),
        ]

        # build_ledger receives only covered recs (caller filters)
        result = build_ledger([covered], gaps, _config(), created_for_year="2027-1")

        assert len(result) == 1
        assert result[0].chapter == _CHAPTER_A
