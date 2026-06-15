"""Unit tests for cause refinement and prescription catalogue (T033, US2).

RED -> GREEN: written before implementation.

SC-003: 학령기 and 만학도 must produce DIFFERENT prescription strings for
the same cause label.

refine_cause: flips cause to '내용난이도' when baseline segment is ALSO
low on the chapter AND hard items are present.
"""

from __future__ import annotations

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    ItemStatistics,
    RetroMesterConfig,
    UnitGap,
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
    chapter_rates: dict[str, float],
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
        "cluster_id": 1 if has_cluster else None,
        "cluster_label": cluster_label,
        "cluster_distance": 0.1 if has_cluster else None,
    }
    base.update(_AXIS_MISSING)
    base.update(_AXIS_RAW)
    base.update(_AXIS_Z)
    return CombinedAnalysisRow(**base)


def _make_item(
    chapter: str,
    expected_difficulty: str = "보통",
    correct_rate: float = 0.5,
) -> ItemStatistics:
    """Build a minimal valid ItemStatistics for testing."""
    return ItemStatistics(
        item_no=1,
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        week=None,
        item_type="이해",
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


def _make_gap(
    chapter: str = "8장",
    segment: str = "학령기",
    cause: str = "기초구멍",
) -> UnitGap:
    """Build a minimal valid UnitGap for testing."""
    return UnitGap(
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        segment=segment,
        segment_mean_rate=0.4,
        n_below=2,
        pct_segment=0.5,
        pct_cohort=0.3,
        is_structural=False,
        cohort_failing_item_types=[],
        cause=cause,
        cause_signals={
            "hard_share": 0.2,
            "item_mean_correct_rate": 0.4,
            "segment_mean_rate": 0.4,
        },
        validity="판정불가",
        unit_importance="중",
        weight=2.0,
        impact_score=4.0,
        evidence_n=4,
    )


def _make_config(
    roster: dict[str, str],
    gap_threshold: float = 0.6,
    baseline_segment: str = "만학도",
) -> RetroMesterConfig:
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
# Tests for prescription_for (SC-003)
# ---------------------------------------------------------------------------


class TestPrescriptionFor:
    """Tests for retro_mester.cause.prescription.prescription_for."""

    def test_학령기_기초구멍_returns_string(self) -> None:
        """prescription_for('기초구멍', '학령기') returns a non-empty string."""
        from retro_mester.cause.prescription import prescription_for

        result = prescription_for("기초구멍", "학령기")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_만학도_기초구멍_returns_string(self) -> None:
        """prescription_for('기초구멍', '만학도') returns a non-empty string."""
        from retro_mester.cause.prescription import prescription_for

        result = prescription_for("기초구멍", "만학도")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_학령기_vs_만학도_different_for_기초구멍(self) -> None:
        """SC-003: 학령기 and 만학도 get DIFFERENT prescriptions for 기초구멍."""
        from retro_mester.cause.prescription import prescription_for

        p_학령기 = prescription_for("기초구멍", "학령기")
        p_만학도 = prescription_for("기초구멍", "만학도")
        assert p_학령기 != p_만학도, (
            f"SC-003: prescriptions must differ per segment; "
            f"got: 학령기={p_학령기!r}, 만학도={p_만학도!r}"
        )

    def test_학령기_vs_만학도_different_for_내용난이도(self) -> None:
        """SC-003: 학령기 and 만학도 get DIFFERENT prescriptions for 내용난이도."""
        from retro_mester.cause.prescription import prescription_for

        p_학령기 = prescription_for("내용난이도", "학령기")
        p_만학도 = prescription_for("내용난이도", "만학도")
        assert p_학령기 != p_만학도, (
            f"SC-003: prescriptions must differ per segment; "
            f"got: 학령기={p_학령기!r}, 만학도={p_만학도!r}"
        )

    def test_미상_cause_returns_default_string(self) -> None:
        """'미상' cause returns a non-empty default prescription for any segment."""
        from retro_mester.cause.prescription import prescription_for

        for segment in ("학령기", "만학도"):
            result = prescription_for("미상", segment)
            assert isinstance(result, str) and len(result) > 0

    def test_all_catalogue_entries_non_empty(self) -> None:
        """Every (cause, segment) combination in the catalogue returns a string."""
        from retro_mester.cause.prescription import prescription_for

        causes = ["기초구멍", "내용난이도", "미상"]
        segments = ["학령기", "만학도"]

        for cause in causes:
            for segment in segments:
                result = prescription_for(cause, segment)
                assert isinstance(result, str) and len(result) > 0, (
                    f"Empty prescription for ({cause!r}, {segment!r})"
                )


# ---------------------------------------------------------------------------
# Tests for refine_cause
# ---------------------------------------------------------------------------


class TestRefineCause:
    """Tests for retro_mester.cause.prescription.refine_cause."""

    def test_baseline_also_low_and_hard_items_flips_to_내용난이도(self) -> None:
        """refine_cause flips to '내용난이도' when baseline low + hard items present."""
        from retro_mester.cause.prescription import refine_cause

        # 학령기 below, 만학도 (baseline) also below
        rows = [
            _make_row("2026000001", {"8장": 0.4}),  # 학령기
            _make_row("2026000002", {"8장": 0.3}),  # 만학도 (baseline)
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")

        # Hard items: expected_difficulty == "어려움"
        items = [_make_item("8장", expected_difficulty="어려움", correct_rate=0.3)]

        gap = _make_gap(chapter="8장", segment="학령기", cause="기초구멍")
        cause, signals = refine_cause(gap, rows, items, config)

        assert cause == "내용난이도", (
            f"Expected '내용난이도' when baseline also low + hard items; got {cause!r}"
        )
        assert "baseline_mean_rate" in signals

    def test_baseline_above_threshold_keeps_us1_cause(self) -> None:
        """When baseline segment is above threshold, US1 cause is preserved."""
        from retro_mester.cause.prescription import refine_cause

        rows = [
            _make_row("2026000001", {"8장": 0.4}),  # 학령기, below
            _make_row("2026000002", {"8장": 0.8}),  # 만학도 (baseline), above
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")

        items = [_make_item("8장", expected_difficulty="어려움", correct_rate=0.3)]

        gap = _make_gap(chapter="8장", segment="학령기", cause="기초구멍")
        cause, _ = refine_cause(gap, rows, items, config)

        assert cause == "기초구멍"

    def test_baseline_low_but_no_hard_items_keeps_us1_cause(self) -> None:
        """Baseline low but no hard items → US1 cause preserved."""
        from retro_mester.cause.prescription import refine_cause

        rows = [
            _make_row("2026000001", {"8장": 0.4}),  # 학령기, below
            _make_row("2026000002", {"8장": 0.3}),  # 만학도 (baseline), below
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")

        # Only easy/medium items — no hard items
        items = [_make_item("8장", expected_difficulty="쉬움", correct_rate=0.7)]

        gap = _make_gap(chapter="8장", segment="학령기", cause="기초구멍")
        cause, _ = refine_cause(gap, rows, items, config)

        assert cause == "기초구멍"

    def test_signals_dict_always_includes_baseline_mean_rate(self) -> None:
        """refine_cause always includes 'baseline_mean_rate' in returned signals."""
        from retro_mester.cause.prescription import refine_cause

        rows = [
            _make_row("2026000001", {"8장": 0.4}),
            _make_row("2026000002", {"8장": 0.8}),
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")
        items = [_make_item("8장")]

        gap = _make_gap(chapter="8장", segment="학령기", cause="기초구멍")
        _, signals = refine_cause(gap, rows, items, config)

        assert "baseline_mean_rate" in signals

    def test_refine_cause_already_내용난이도_remains(self) -> None:
        """If US1 already labeled '내용난이도', refine_cause keeps it."""
        from retro_mester.cause.prescription import refine_cause

        rows = [
            _make_row("2026000001", {"8장": 0.4}),
            _make_row("2026000002", {"8장": 0.8}),
        ]
        roster = {"2026000001": "학령기", "2026000002": "만학도"}
        config = _make_config(roster=roster, baseline_segment="만학도")
        items = [_make_item("8장", expected_difficulty="어려움")]

        gap = _make_gap(chapter="8장", segment="학령기", cause="내용난이도")
        cause, _ = refine_cause(gap, rows, items, config)

        assert cause == "내용난이도"
