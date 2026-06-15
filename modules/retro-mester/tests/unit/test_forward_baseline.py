"""T037 — Unit tests for forward/baseline.py: build_baseline.

RED phase: written before implementation.  All tests must FAIL until
``retro_mester.forward.baseline.build_baseline`` is implemented.
"""

from __future__ import annotations

import pytest

from paideia_shared.schemas import CombinedAnalysisRow, RetroMesterConfig


# ---------------------------------------------------------------------------
# Helpers
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

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_CHAPTER_A = "1장 해부학 서론"
_CHAPTER_B = "2장 세포와 조직"


def _row(
    student_id: str,
    chapter_rates: dict[str, float],
    segment: str = "학령기",
) -> CombinedAnalysisRow:
    """Build a minimal CombinedAnalysisRow for baseline tests."""
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
    }
    for axis in _AXES:
        d[f"{axis}_raw"] = None
        d[f"{axis}_z"] = None
        d[f"{axis}_missing"] = True
    return CombinedAnalysisRow(**d)


def _config(roster: dict[str, str]) -> RetroMesterConfig:
    """Build a minimal RetroMesterConfig."""
    return RetroMesterConfig(
        semester=_SEMESTER,
        course_slug=_COURSE,
        group_roster=roster,
        unit_importance={_CHAPTER_A: "상", _CHAPTER_B: "중"},
        gap_threshold=0.6,
        baseline_segment="만학도",
        low_discrimination_threshold=0.2,
        cognitive_cliff_drop=0.15,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildBaseline:
    """T037: build_baseline emits one BaselineSnapshotRow per (segment × chapter)."""

    def test_emits_one_row_per_segment_chapter(self) -> None:
        """Each (segment, chapter) pair produces exactly one snapshot row."""
        from retro_mester.forward.baseline import build_baseline

        roster = {
            "2026000001": "학령기",
            "2026000002": "학령기",
            "2026000003": "만학도",
            "2026000004": "만학도",
        }
        rows = [
            _row("2026000001", {_CHAPTER_A: 0.4, _CHAPTER_B: 0.5}, segment="학령기"),
            _row("2026000002", {_CHAPTER_A: 0.5, _CHAPTER_B: 0.55}, segment="학령기"),
            _row("2026000003", {_CHAPTER_A: 0.7, _CHAPTER_B: 0.8}, segment="만학도"),
            _row("2026000004", {_CHAPTER_A: 0.6, _CHAPTER_B: 0.75}, segment="만학도"),
        ]
        config = _config(roster)
        result = build_baseline(rows, config)

        # 2 segments × 2 chapters = 4 rows
        assert len(result) == 4

        keys = {(r.segment, r.chapter) for r in result}
        assert ("학령기", _CHAPTER_A) in keys
        assert ("학령기", _CHAPTER_B) in keys
        assert ("만학도", _CHAPTER_A) in keys
        assert ("만학도", _CHAPTER_B) in keys

    def test_correct_rate_is_segment_mean(self) -> None:
        """correct_rate is the mean of chapter_correct_rates for the segment."""
        from retro_mester.forward.baseline import build_baseline

        roster = {
            "2026000001": "학령기",
            "2026000002": "학령기",
        }
        rows = [
            _row("2026000001", {_CHAPTER_A: 0.4}, segment="학령기"),
            _row("2026000002", {_CHAPTER_A: 0.6}, segment="학령기"),
        ]
        config = _config(roster)
        result = build_baseline(rows, config)

        snap = next(r for r in result if r.segment == "학령기" and r.chapter == _CHAPTER_A)
        assert abs(snap.correct_rate - 0.5) < 1e-9

    def test_n_is_student_count_with_data(self) -> None:
        """n reflects the number of students who have data for that chapter."""
        from retro_mester.forward.baseline import build_baseline

        roster = {
            "2026000001": "학령기",
            "2026000002": "학령기",
            "2026000003": "학령기",
        }
        # Only 2 of 3 have data for CHAPTER_A
        rows = [
            _row("2026000001", {_CHAPTER_A: 0.4}, segment="학령기"),
            _row("2026000002", {_CHAPTER_A: 0.6}, segment="학령기"),
            _row("2026000003", {_CHAPTER_B: 0.5}, segment="학령기"),  # no CHAPTER_A
        ]
        config = _config(roster)
        result = build_baseline(rows, config)

        snap_a = next(r for r in result if r.segment == "학령기" and r.chapter == _CHAPTER_A)
        assert snap_a.n == 2

    def test_cognitive_level_is_전체(self) -> None:
        """All rows use cognitive_level='전체' (per-cognitive-level deferred)."""
        from retro_mester.forward.baseline import build_baseline

        roster = {"2026000001": "학령기"}
        rows = [_row("2026000001", {_CHAPTER_A: 0.5})]
        config = _config(roster)
        result = build_baseline(rows, config)

        assert all(r.cognitive_level == "전체" for r in result)

    def test_semester_and_course_slug_carried(self) -> None:
        """semester and course_slug from config are on every snapshot row."""
        from retro_mester.forward.baseline import build_baseline

        roster = {"2026000001": "학령기"}
        rows = [_row("2026000001", {_CHAPTER_A: 0.5})]
        config = _config(roster)
        result = build_baseline(rows, config)

        for snap in result:
            assert snap.semester == _SEMESTER
            assert snap.course_slug == _COURSE

    def test_off_roster_students_excluded(self) -> None:
        """Students absent from group_roster are excluded from baseline."""
        from retro_mester.forward.baseline import build_baseline

        roster = {"2026000001": "학령기"}  # only one in roster
        rows = [
            _row("2026000001", {_CHAPTER_A: 0.4}),
            _row("2026000099", {_CHAPTER_A: 0.8}),  # not in roster
        ]
        config = _config(roster)
        result = build_baseline(rows, config)

        snap = next(r for r in result if r.chapter == _CHAPTER_A)
        # Only 1 student → mean is 0.4, not (0.4+0.8)/2=0.6
        assert abs(snap.correct_rate - 0.4) < 1e-9
        assert snap.n == 1

    def test_empty_rows_returns_empty(self) -> None:
        """build_baseline with no rows returns empty list."""
        from retro_mester.forward.baseline import build_baseline

        config = _config({})
        result = build_baseline([], config)
        assert result == []
