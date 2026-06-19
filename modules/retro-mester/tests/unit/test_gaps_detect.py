"""Unit tests for segment assignment + gap detection (T021).

RED -> GREEN: written before implementation.

Tests cover:
- assign_segments: roster lookup, unclassified exclusion
- detect_gaps: threshold emit/skip, n_below, evidence_n, impact math, segment bucketing
"""

from __future__ import annotations

import math

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    InsufficientEvidenceUnit,
    ItemStatistics,
    RetroMesterConfig,
    UnitGap,
)
from retro_mester.gaps.detect import detect_gaps
from retro_mester.segment.assign import assign_segments

# ---------------------------------------------------------------------------
# Factories for minimal valid Pydantic objects
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
    exam_taken: bool = True,
    name_kr: str | None = None,
) -> CombinedAnalysisRow:
    """Build a minimal valid CombinedAnalysisRow for testing."""
    base = {
        "student_id": student_id,
        "name_kr": name_kr,
        "on_roster": True,
        "section": None,
        "semester": "2026-1",
        "course_slug": "anatomy",
        "exam_taken": exam_taken,
        "total_score": 70.0 if exam_taken else None,
        "score_percent": 70.0 if exam_taken else None,
        "section_percentile": 50.0 if exam_taken else None,
        "cohort_percentile": 50.0 if exam_taken else None,
        "z_score": 0.0 if exam_taken else None,
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
        "시험응시": exam_taken,
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


def _make_item(
    chapter: str,
    expected_difficulty: str = "보통",
    correct_rate: float = 0.65,
    item_type: str = "이해",
) -> ItemStatistics:
    """Build a minimal valid ItemStatistics for testing."""
    return ItemStatistics(
        item_no=1,
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        week=None,
        item_type=item_type,
        difficulty_level=3,
        expected_difficulty=expected_difficulty,
        source="교과서",
        correct_answer=1,
        n_responders=20,
        n_correct=max(0, round(correct_rate * 20)),
        n_omit=0,
        correct_rate=correct_rate,
        omit_rate=0.0,
        discrimination_index=0.3,
        point_biserial=0.3,
        top_distractor_no=None,
        top_distractor_rate=None,
        is_top_distractor_adjacent=False,
        option_distribution={
            1: correct_rate,
            2: (1 - correct_rate) / 4,
            3: (1 - correct_rate) / 4,
            4: (1 - correct_rate) / 4,
            5: (1 - correct_rate) / 4,
        },
        distractor_label="특이사항 없음",
    )


def _make_config(
    roster: dict[str, str],
    unit_importance: dict[str, str] | None = None,
    gap_threshold: float = 0.6,
    effort_ratings: dict[str, str] | None = None,
) -> RetroMesterConfig:
    """Build a minimal valid RetroMesterConfig for testing."""
    return RetroMesterConfig(
        semester="2026-1",
        course_slug="anatomy",
        group_roster=roster,
        unit_importance=unit_importance or {},
        gap_threshold=gap_threshold,
        effort_ratings=effort_ratings or {},
    )


# ===========================================================================
# T021-A: assign_segments
# ===========================================================================


class TestAssignSegments:
    """Tests for retro_mester.segment.assign.assign_segments."""

    def test_basic_bucketing(self) -> None:
        """Students in roster are sorted into their segments."""
        rows = [
            _make_row("2026000001", {"8장": 0.5}),
            _make_row("2026000002", {"8장": 0.7}),
        ]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "만학도"},
        )
        buckets, unclassified = assign_segments(rows, config)

        assert len(buckets["학령기"]) == 1
        assert buckets["학령기"][0].student_id == "2026000001"
        assert len(buckets["만학도"]) == 1
        assert buckets["만학도"][0].student_id == "2026000002"
        assert unclassified == []

    def test_unclassified_excluded(self) -> None:
        """Students not in roster appear in unclassified list, not in segment buckets."""
        rows = [
            _make_row("2026000001", {"8장": 0.5}),
            _make_row("2026000099", {"8장": 0.3}),  # not in roster
        ]
        config = _make_config(roster={"2026000001": "학령기"})
        buckets, unclassified = assign_segments(rows, config)

        assert len(buckets.get("학령기", [])) == 1
        assert "2026000099" in unclassified
        total_in_buckets = sum(len(v) for v in buckets.values())
        assert total_in_buckets == 1

    def test_all_unclassified(self) -> None:
        """If roster is empty, all students are unclassified."""
        rows = [_make_row("2026000001", {"8장": 0.5})]
        config = _make_config(roster={})
        buckets, unclassified = assign_segments(rows, config)

        total_in_buckets = sum(len(v) for v in buckets.values())
        assert total_in_buckets == 0
        assert "2026000001" in unclassified

    def test_empty_rows(self) -> None:
        """Empty rows input yields empty buckets and empty unclassified."""
        config = _make_config(roster={"2026000001": "학령기"})
        buckets, unclassified = assign_segments([], config)

        total = sum(len(v) for v in buckets.values())
        assert total == 0
        assert unclassified == []

    def test_multiple_students_same_segment(self) -> None:
        """Multiple students in the same segment all appear in that bucket."""
        rows = [
            _make_row("2026000001", {"8장": 0.5}),
            _make_row("2026000002", {"8장": 0.4}),
            _make_row("2026000003", {"8장": 0.3}),
        ]
        config = _make_config(
            roster={
                "2026000001": "학령기",
                "2026000002": "학령기",
                "2026000003": "만학도",
            }
        )
        buckets, unclassified = assign_segments(rows, config)

        assert len(buckets["학령기"]) == 2
        assert len(buckets["만학도"]) == 1
        assert unclassified == []


# ===========================================================================
# T021-B: detect_gaps
# ===========================================================================


class TestDetectGaps:
    """Tests for retro_mester.gaps.detect.detect_gaps."""

    def _two_segment_setup(
        self,
        seg1_rate: float,
        seg2_rate: float,
        gap_threshold: float = 0.6,
        importance: str = "중",
    ) -> tuple[list[CombinedAnalysisRow], list[ItemStatistics], RetroMesterConfig]:
        """Return rows, items, config for a simple 2-student, 1-chapter scenario."""
        rows = [
            _make_row("2026000001", {"8장": seg1_rate}),
            _make_row("2026000002", {"8장": seg2_rate}),
        ]
        items = [_make_item("8장", expected_difficulty="보통", correct_rate=0.5)]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "만학도"},
            unit_importance={"8장": importance},
        )
        return rows, items, config

    def test_below_threshold_emits_gap(self) -> None:
        """segment_mean_rate < gap_threshold → UnitGap emitted."""
        rows, items, config = self._two_segment_setup(seg1_rate=0.4, seg2_rate=0.7)
        gaps, _insufficient = detect_gaps(rows, items, config)

        chapters = {g.chapter for g in gaps}
        segments = {g.segment for g in gaps}
        assert "8장" in chapters
        assert "학령기" in segments

    def test_above_threshold_no_gap(self) -> None:
        """segment_mean_rate >= gap_threshold → no UnitGap for that segment."""
        rows, items, config = self._two_segment_setup(seg1_rate=0.8, seg2_rate=0.9)
        gaps, _insufficient = detect_gaps(rows, items, config)

        assert len(gaps) == 0

    def test_at_threshold_no_gap(self) -> None:
        """segment_mean_rate == gap_threshold exactly → no gap (strict < required)."""
        rows, items, config = self._two_segment_setup(seg1_rate=0.6, seg2_rate=0.9)
        gaps, _insufficient = detect_gaps(rows, items, config)

        assert all(g.segment != "학령기" for g in gaps)

    def test_n_below_count(self) -> None:
        """n_below equals count of segment students below threshold."""
        # 3 학령기 students: rates 0.3, 0.4, 0.7 → 2 below 0.6
        rows = [
            _make_row("2026000001", {"8장": 0.3}),
            _make_row("2026000002", {"8장": 0.4}),
            _make_row("2026000003", {"8장": 0.7}),
        ]
        items = [_make_item("8장")]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "학령기", "2026000003": "학령기"},
            unit_importance={"8장": "중"},
        )
        gaps, _insufficient = detect_gaps(rows, items, config)

        assert len(gaps) == 1
        gap = gaps[0]
        assert gap.n_below == 2

    def test_evidence_n(self) -> None:
        """evidence_n equals students with data for the chapter (not skipping)."""
        rows = [
            _make_row("2026000001", {"8장": 0.3}),
            _make_row("2026000002", {"8장": 0.4}),
            # This student has no entry for '8장'
            _make_row("2026000003", {}),
        ]
        items = [_make_item("8장")]
        config = _make_config(
            roster={
                "2026000001": "학령기",
                "2026000002": "학령기",
                "2026000003": "학령기",
            },
        )
        gaps, _insufficient = detect_gaps(rows, items, config)

        assert len(gaps) == 1
        gap = gaps[0]
        # evidence_n = 2 (student 3 lacks chapter key, skipped)
        assert gap.evidence_n == 2

    def test_impact_math(self) -> None:
        """impact_score == n_below * weight (UnitGap V2 invariant from detect)."""
        rows = [
            _make_row("2026000001", {"8장": 0.3}),
            _make_row("2026000002", {"8장": 0.4}),
        ]
        items = [_make_item("8장")]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "학령기"},
            unit_importance={"8장": "상"},
        )
        gaps, _insufficient = detect_gaps(rows, items, config)

        assert len(gaps) == 1
        gap = gaps[0]
        expected = gap.n_below * gap.weight
        assert math.isclose(gap.impact_score, expected, rel_tol=1e-9)

    def test_pct_segment_and_cohort(self) -> None:
        """pct_segment and pct_cohort computed correctly."""
        # 2 학령기 (both below 0.6), 1 만학도 (above 0.6)
        rows = [
            _make_row("2026000001", {"8장": 0.3}),
            _make_row("2026000002", {"8장": 0.4}),
            _make_row("2026000003", {"8장": 0.9}),
        ]
        items = [_make_item("8장")]
        config = _make_config(
            roster={
                "2026000001": "학령기",
                "2026000002": "학령기",
                "2026000003": "만학도",
            },
        )
        gaps, _insufficient = detect_gaps(rows, items, config)

        학령기_gap = next(g for g in gaps if g.segment == "학령기")
        # pct_segment = 2/2 = 1.0
        assert math.isclose(학령기_gap.pct_segment, 1.0, rel_tol=1e-9)
        # pct_cohort = 2/3 ≈ 0.667 (all 3 students have chapter data; 2 below threshold)
        assert math.isclose(학령기_gap.pct_cohort, 2 / 3, rel_tol=1e-6)

    def test_segment_bucketing_separate_gaps(self) -> None:
        """Both segments can emit gaps if both are below threshold."""
        rows = [
            _make_row("2026000001", {"8장": 0.3}),  # 학령기, below
            _make_row("2026000002", {"8장": 0.4}),  # 만학도, below
        ]
        items = [_make_item("8장")]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "만학도"},
        )
        gaps, _insufficient = detect_gaps(rows, items, config)

        segments_with_gap = {g.segment for g in gaps}
        assert "학령기" in segments_with_gap
        assert "만학도" in segments_with_gap

    def test_unclassified_excluded_from_gaps(self) -> None:
        """Students not in roster do not contribute to any gap calculation."""
        rows = [
            _make_row("2026000001", {"8장": 0.3}),  # in roster
            _make_row("2026000099", {"8장": 0.1}),  # NOT in roster
        ]
        items = [_make_item("8장")]
        config = _make_config(roster={"2026000001": "학령기"})
        gaps, _insufficient = detect_gaps(rows, items, config)

        # Only student 001 counted; n_below=1, evidence_n=1
        assert len(gaps) == 1
        gap = gaps[0]
        assert gap.evidence_n == 1
        assert gap.n_below == 1

    def test_default_importance_falls_back_to_중(self) -> None:
        """Chapters not in unit_importance default to '중'."""
        rows = [_make_row("2026000001", {"9장": 0.3})]
        items = [_make_item("9장")]
        config = _make_config(
            roster={"2026000001": "학령기"},
            unit_importance={},  # no entry for 9장
        )
        gaps, _insufficient = detect_gaps(rows, items, config)

        assert len(gaps) == 1
        gap = gaps[0]
        assert gap.unit_importance == "중"
        assert gap.weight == config.importance_weights["중"]

    def test_provisional_defaults_set(self) -> None:
        """Provisional fields are set to documented US1 defaults."""
        rows = [_make_row("2026000001", {"8장": 0.3})]
        items = [_make_item("8장")]
        config = _make_config(roster={"2026000001": "학령기"})
        gaps, _insufficient = detect_gaps(rows, items, config)

        gap = gaps[0]
        assert gap.is_structural is False
        assert gap.cohort_failing_item_types == []
        assert gap.validity == "판정불가"

    def test_no_items_uses_empty_signals(self) -> None:
        """Chapter with no items still emits a gap (cause='미상')."""
        rows = [_make_row("2026000001", {"8장": 0.3})]
        items: list[ItemStatistics] = []
        config = _make_config(roster={"2026000001": "학령기"})
        gaps, _insufficient = detect_gaps(rows, items, config)

        assert len(gaps) == 1
        assert gaps[0].cause == "미상"

    def test_returns_unit_gap_instances(self) -> None:
        """detect_gaps returns a 2-tuple whose first element is UnitGap objects."""
        rows = [_make_row("2026000001", {"8장": 0.3})]
        items = [_make_item("8장")]
        config = _make_config(roster={"2026000001": "학령기"})
        gaps, _insufficient = detect_gaps(rows, items, config)

        assert all(isinstance(g, UnitGap) for g in gaps)

    def test_evidence_n_zero_skipped(self) -> None:
        """If no segment students have data for a chapter, no gap is emitted."""
        rows = [
            _make_row("2026000001", {}),  # no chapter data at all
        ]
        items = [_make_item("8장")]
        config = _make_config(roster={"2026000001": "학령기"})
        gaps, _insufficient = detect_gaps(rows, items, config)

        # evidence_n = 0 → skipped (not emitted)
        assert len(gaps) == 0


# ===========================================================================
# T008: InsufficientEvidenceUnit emission (no-silent-omission, H1)
# ===========================================================================


class TestInsufficientEvidence:
    """Tests for the 근거부족 (insufficient-evidence) emission in detect_gaps.

    Emit condition: a chapter present in the items/data universe but with ZERO
    answer-data students across the ENTIRE cohort (``total_cohort_n == 0``).
    A chapter taken by only one segment must NOT produce insufficient units.
    """

    def test_returns_two_tuple(self) -> None:
        """detect_gaps returns (gaps, insufficient) where insufficient is a list."""
        rows = [_make_row("2026000001", {"8장": 0.3})]
        items = [_make_item("8장")]
        config = _make_config(roster={"2026000001": "학령기"})
        result = detect_gaps(rows, items, config)

        assert isinstance(result, tuple)
        gaps, insufficient = result
        assert isinstance(gaps, list)
        assert isinstance(insufficient, list)

    def test_fully_empty_chapter_emits_insufficient(self) -> None:
        """A chapter with zero answer-data in ANY segment → InsufficientEvidenceUnit.

        '9장' is only present via items (no student reports it), so the whole
        cohort has zero evidence for it.  It must surface as an insufficient
        unit per (chapter, segment), NOT be silently dropped, and must NOT
        appear in gaps.
        """
        rows = [
            _make_row("2026000001", {"8장": 0.3}),  # 학령기, has 8장 only
            _make_row("2026000002", {"8장": 0.4}),  # 만학도, has 8장 only
        ]
        # '9장' has items but no student answer data anywhere.
        items = [_make_item("8장"), _make_item("9장")]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "만학도"},
        )
        gaps, insufficient = detect_gaps(rows, items, config)

        # 9장 must not be in gaps (no evidence to compute a rate).
        assert all(g.chapter != "9장" for g in gaps)

        # 9장 must be in insufficient, one unit per segment bucket.
        nine = [u for u in insufficient if u.chapter == "9장"]
        assert len(nine) == 2, f"expected one 9장 unit per segment, got {len(nine)}"
        assert {u.segment for u in nine} == {"학령기", "만학도"}
        for u in nine:
            assert isinstance(u, InsufficientEvidenceUnit)
            assert u.evidence_n == 0
            assert u.reason == "근거부족-자료없음"
            assert u.semester == "2026-1"
            assert u.course_slug == "anatomy"

    def test_single_segment_covered_chapter_no_insufficient(self) -> None:
        """A chapter covered by only ONE segment yields NO insufficient unit.

        '8장' is answered only by the 학령기 student; the 만학도 student has
        no 8장 entry.  total_cohort_n > 0, so the empty 만학도 segment must NOT
        emit an insufficient unit (that would distort uncovered_ratio, FR-015).
        """
        rows = [
            _make_row("2026000001", {"8장": 0.3}),  # 학령기 covers 8장
            _make_row("2026000002", {}),  # 만학도 covers nothing
        ]
        items = [_make_item("8장")]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "만학도"},
        )
        gaps, insufficient = detect_gaps(rows, items, config)

        # 8장 has cohort evidence (학령기) → no insufficient unit at all.
        assert insufficient == []
        # The 학령기 gap is still detected.
        assert any(g.chapter == "8장" and g.segment == "학령기" for g in gaps)
