"""T046 — Unit tests for align/interest_gap.py.

RED phase: all tests must fail until align/interest_gap.py is implemented.

FR-022: Self-report bias must be flagged; interest/aversion gaps are presented
conservatively with an explicit note.

interest_aversion_findings() contract:
- Computes cohort mean of interest_chapters_correct_rate and
  aversion_chapters_correct_rate from rows where these fields are not None.
- Returns a dict with keys:
    'interest_mean': float | None   — cohort mean interest rate (None if no data)
    'aversion_mean': float | None   — cohort mean aversion rate (None if no data)
    'gap': float | None             — interest_mean - aversion_mean (None if either absent)
    'n_interest': int               — count of students with interest_chapters_correct_rate
    'n_aversion': int               — count of students with aversion_chapters_correct_rate
    'bias_note': str                — FR-022 self-report bias note (always present)
- 'bias_note' must contain '자가응답' or 'self-report' (case-insensitive).
"""

from __future__ import annotations

from paideia_shared.schemas import CombinedAnalysisRow

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


def _make_row(
    student_id: str,
    interest_rate: float | None = None,
    aversion_rate: float | None = None,
) -> CombinedAnalysisRow:
    axis_fields: dict = {}
    for ax in _AXES:
        axis_fields[f"{ax}_raw"] = None
        axis_fields[f"{ax}_z"] = None
        axis_fields[f"{ax}_missing"] = True
    return CombinedAnalysisRow(
        student_id=student_id,
        name_kr=None,
        on_roster=True,
        section=None,
        semester="2026-1",
        course_slug="anatomy",
        cluster_id=None,
        cluster_label=None,
        cluster_distance=None,
        exam_taken=True,
        total_score=60.0,
        score_percent=60.0,
        section_percentile=50.0,
        cohort_percentile=50.0,
        z_score=0.0,
        chapter_correct_rates={},
        source_correct_rates={},
        difficulty_correct_rates={},
        expected_difficulty_correct_rates={},
        item_type_correct_rates={},
        interest_chapters_correct_rate=interest_rate,
        aversion_chapters_correct_rate=aversion_rate,
        prior_readiness_q5=None,
        prior_readiness_q6=None,
        time_pattern_q21=None,
        time_pattern_q22=None,
        time_pattern_q23=None,
        interest_topics_q9=None,
        interest_topics_q10=None,
        interest_topics_q11=None,
        categorical_intent_q12=None,
        categorical_intent_q13=None,
        진단응답=False,
        시험응시=True,
        needs_map_schema_version="0.1.1",
        immersio_phase2_schema_version="0.1.0",
        **axis_fields,
    )


class TestInterestAversionFindings:
    """Tests for interest_aversion_findings()."""

    def test_gap_computed_correctly(self) -> None:
        """gap = interest_mean - aversion_mean."""
        from retro_mester.align.interest_gap import interest_aversion_findings

        rows = [
            _make_row("2026000001", interest_rate=0.80, aversion_rate=0.50),
            _make_row("2026000002", interest_rate=0.70, aversion_rate=0.60),
        ]
        result = interest_aversion_findings(rows)
        assert abs(result["interest_mean"] - 0.75) < 1e-9
        assert abs(result["aversion_mean"] - 0.55) < 1e-9
        assert abs(result["gap"] - 0.20) < 1e-9

    def test_interest_mean_none_when_no_data(self) -> None:
        """When no rows have interest data, interest_mean is None."""
        from retro_mester.align.interest_gap import interest_aversion_findings

        rows = [_make_row("2026000001", interest_rate=None, aversion_rate=0.50)]
        result = interest_aversion_findings(rows)
        assert result["interest_mean"] is None
        assert result["gap"] is None

    def test_aversion_mean_none_when_no_data(self) -> None:
        """When no rows have aversion data, aversion_mean is None."""
        from retro_mester.align.interest_gap import interest_aversion_findings

        rows = [_make_row("2026000001", interest_rate=0.80, aversion_rate=None)]
        result = interest_aversion_findings(rows)
        assert result["aversion_mean"] is None
        assert result["gap"] is None

    def test_counts_correct(self) -> None:
        """n_interest and n_aversion count non-None values."""
        from retro_mester.align.interest_gap import interest_aversion_findings

        rows = [
            _make_row("2026000001", interest_rate=0.80, aversion_rate=0.50),
            _make_row("2026000002", interest_rate=None, aversion_rate=0.60),
            _make_row("2026000003", interest_rate=0.70, aversion_rate=None),
        ]
        result = interest_aversion_findings(rows)
        assert result["n_interest"] == 2
        assert result["n_aversion"] == 2

    def test_bias_note_always_present(self) -> None:
        """bias_note is always a non-empty string."""
        from retro_mester.align.interest_gap import interest_aversion_findings

        rows = [_make_row("2026000001")]
        result = interest_aversion_findings(rows)
        assert "bias_note" in result
        assert isinstance(result["bias_note"], str)
        assert len(result["bias_note"]) > 0

    def test_bias_note_mentions_self_report(self) -> None:
        """bias_note mentions '자가응답' or 'self-report' (FR-022)."""
        from retro_mester.align.interest_gap import interest_aversion_findings

        rows = [_make_row("2026000001")]
        result = interest_aversion_findings(rows)
        note = result["bias_note"].lower()
        assert "자가응답" in note or "self-report" in note

    def test_empty_rows_returns_nones(self) -> None:
        """Empty row list → both means None, gap None."""
        from retro_mester.align.interest_gap import interest_aversion_findings

        result = interest_aversion_findings([])
        assert result["interest_mean"] is None
        assert result["aversion_mean"] is None
        assert result["gap"] is None
        assert result["n_interest"] == 0
        assert result["n_aversion"] == 0

    def test_partial_none_mix(self) -> None:
        """Some rows have only one side populated — correct counts and means."""
        from retro_mester.align.interest_gap import interest_aversion_findings

        rows = [
            _make_row("2026000001", interest_rate=0.80, aversion_rate=0.50),
            _make_row("2026000002", interest_rate=0.60, aversion_rate=None),
        ]
        result = interest_aversion_findings(rows)
        assert abs(result["interest_mean"] - 0.70) < 1e-9  # mean(0.80, 0.60)
        assert abs(result["aversion_mean"] - 0.50) < 1e-9  # only one value
        assert result["n_interest"] == 2
        assert result["n_aversion"] == 1
        # gap can only be computed if both means are present
        assert result["gap"] is not None
        assert abs(result["gap"] - 0.20) < 1e-9
