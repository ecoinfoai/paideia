"""Unit tests for cluster vocabulary extraction (T034, US2).

RED -> GREEN: written before implementation.

segment_cluster_vocab(rows, config) -> dict[SegmentKey, str | None]

For each segment: most common non-null cluster_label among that segment's
students.  None when no student in the segment has a non-null cluster_label.
"""

from __future__ import annotations

import pytest

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    RetroMesterConfig,
)

# ---------------------------------------------------------------------------
# Minimal factories
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
    cluster_label: str | None = None,
) -> CombinedAnalysisRow:
    """Build a minimal valid CombinedAnalysisRow for testing."""
    has_cluster = cluster_label is not None
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
        "chapter_correct_rates": {"8장": 0.5},
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
        "cluster_id": 1 if has_cluster else None,
        "cluster_label": cluster_label,
        "cluster_distance": 0.1 if has_cluster else None,
    }
    base.update(_AXIS_MISSING)
    base.update(_AXIS_RAW)
    base.update(_AXIS_Z)
    return CombinedAnalysisRow(**base)


def _make_config(roster: dict[str, str]) -> RetroMesterConfig:
    return RetroMesterConfig(
        semester="2026-1",
        course_slug="anatomy",
        group_roster=roster,
        unit_importance={},
        effort_ratings={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSegmentClusterVocab:
    """Tests for retro_mester.segment.vocab.segment_cluster_vocab."""

    def test_most_common_label_returned(self) -> None:
        """Most-frequent non-null cluster_label is returned for a segment."""
        from retro_mester.segment.vocab import segment_cluster_vocab

        rows = [
            _make_row("2026000001", cluster_label="전략적"),  # 학령기
            _make_row("2026000002", cluster_label="전략적"),  # 학령기 (same)
            _make_row("2026000003", cluster_label="수동적"),  # 학령기 (minority)
        ]
        config = _make_config(
            roster={
                "2026000001": "학령기",
                "2026000002": "학령기",
                "2026000003": "학령기",
            }
        )
        result = segment_cluster_vocab(rows, config)

        assert result.get("학령기") == "전략적"

    def test_none_when_no_cluster_labels(self) -> None:
        """Returns None for a segment when all students have null cluster_label."""
        from retro_mester.segment.vocab import segment_cluster_vocab

        rows = [
            _make_row("2026000001", cluster_label=None),
            _make_row("2026000002", cluster_label=None),
        ]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "학령기"}
        )
        result = segment_cluster_vocab(rows, config)

        assert result.get("학령기") is None

    def test_two_segments_independent_vocab(self) -> None:
        """Each segment gets its own most-common label."""
        from retro_mester.segment.vocab import segment_cluster_vocab

        rows = [
            _make_row("2026000001", cluster_label="전략적"),   # 학령기
            _make_row("2026000002", cluster_label="전략적"),   # 학령기
            _make_row("2026000003", cluster_label="습관중심"),  # 만학도
            _make_row("2026000004", cluster_label="습관중심"),  # 만학도
        ]
        config = _make_config(
            roster={
                "2026000001": "학령기",
                "2026000002": "학령기",
                "2026000003": "만학도",
                "2026000004": "만학도",
            }
        )
        result = segment_cluster_vocab(rows, config)

        assert result.get("학령기") == "전략적"
        assert result.get("만학도") == "습관중심"

    def test_unclassified_students_excluded(self) -> None:
        """Students not in roster do not contribute to vocab."""
        from retro_mester.segment.vocab import segment_cluster_vocab

        rows = [
            _make_row("2026000001", cluster_label="전략적"),   # in roster
            _make_row("2026000099", cluster_label="수동적"),   # NOT in roster
        ]
        config = _make_config(roster={"2026000001": "학령기"})
        result = segment_cluster_vocab(rows, config)

        # Only 전략적 (from 001) should count; 수동적 from 099 excluded
        assert result.get("학령기") == "전략적"

    def test_tie_broken_deterministically(self) -> None:
        """When two labels tie, the function returns one consistently."""
        from retro_mester.segment.vocab import segment_cluster_vocab

        rows = [
            _make_row("2026000001", cluster_label="A"),
            _make_row("2026000002", cluster_label="B"),
        ]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "학령기"}
        )
        # Just assert it returns some string (not None) on a tie
        result = segment_cluster_vocab(rows, config)
        assert result.get("학령기") is not None

    def test_mixed_null_and_non_null_ignores_null(self) -> None:
        """Null cluster_labels are ignored; only non-null ones count."""
        from retro_mester.segment.vocab import segment_cluster_vocab

        rows = [
            _make_row("2026000001", cluster_label=None),    # 학령기, no cluster
            _make_row("2026000002", cluster_label="전략적"),  # 학령기, has cluster
        ]
        config = _make_config(
            roster={"2026000001": "학령기", "2026000002": "학령기"}
        )
        result = segment_cluster_vocab(rows, config)

        # Null excluded → 전략적 wins
        assert result.get("학령기") == "전략적"

    def test_empty_rows_returns_empty_dict(self) -> None:
        """Empty rows input yields empty dict."""
        from retro_mester.segment.vocab import segment_cluster_vocab

        config = _make_config(roster={"2026000001": "학령기"})
        result = segment_cluster_vocab([], config)

        assert result == {}
