"""Unit tests for cause classification (T023).

RED -> GREEN: written before implementation.

Tests cover the three CauseLabel outcomes:
- 내용난이도: hard_share >= 0.5
- 기초구멍: hard_share < 0.5 AND mean correct_rate low
- 미상: no items for chapter
"""

from __future__ import annotations

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    ItemStatistics,
    RetroMesterConfig,
)
from retro_mester.cause.classify import classify_cause

# ---------------------------------------------------------------------------
# Factories (copy-minimal from test_gaps_detect to avoid inter-test coupling)
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
    base = {
        "student_id": student_id,
        "name_kr": None,
        "on_roster": True,
        "section": None,
        "semester": "2026-1",
        "course_slug": "anatomy",
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
) -> ItemStatistics:
    n_responders = 20
    n_correct = max(0, round(correct_rate * n_responders))
    n_correct = min(n_correct, n_responders)
    # build an option_distribution that sums <=1.0
    wrong_share = (1.0 - correct_rate) / 4
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
        n_responders=n_responders,
        n_correct=n_correct,
        n_omit=0,
        correct_rate=correct_rate,
        omit_rate=0.0,
        discrimination_index=0.3,
        point_biserial=0.3,
        top_distractor_no=None,
        top_distractor_rate=None,
        is_top_distractor_adjacent=False,
        option_distribution={1: correct_rate, 2: wrong_share, 3: wrong_share, 4: wrong_share, 5: wrong_share},
        distractor_label="특이사항 없음",
    )


def _make_config() -> RetroMesterConfig:
    return RetroMesterConfig(
        semester="2026-1",
        course_slug="anatomy",
        group_roster={"2026000001": "학령기"},
        unit_importance={},
    )


# ===========================================================================
# Tests for classify_cause
# ===========================================================================


class TestClassifyCause:
    """Tests for retro_mester.cause.classify.classify_cause."""

    def test_all_hard_items_yields_내용난이도(self) -> None:
        """hard_share >= 0.5 → 내용난이도."""
        items = [
            _make_item("8장", expected_difficulty="어려움", correct_rate=0.3),
            _make_item("8장", expected_difficulty="어려움", correct_rate=0.25),
        ]
        rows = [_make_row("2026000001", {"8장": 0.3})]
        config = _make_config()

        label, signals = classify_cause("8장", "학령기", rows, items, config)

        assert label == "내용난이도"

    def test_half_hard_items_yields_내용난이도(self) -> None:
        """hard_share == 0.5 → 내용난이도 (boundary: >= 0.5)."""
        items = [
            _make_item("8장", expected_difficulty="어려움", correct_rate=0.3),
            _make_item("8장", expected_difficulty="보통", correct_rate=0.5),
        ]
        rows = [_make_row("2026000001", {"8장": 0.4})]
        config = _make_config()

        label, signals = classify_cause("8장", "학령기", rows, items, config)

        assert label == "내용난이도"

    def test_easy_items_low_rate_yields_기초구멍(self) -> None:
        """hard_share < 0.5 AND mean correct_rate low → 기초구멍."""
        # All 쉬움/보통 items → hard_share = 0
        items = [
            _make_item("8장", expected_difficulty="쉬움", correct_rate=0.2),
            _make_item("8장", expected_difficulty="보통", correct_rate=0.25),
        ]
        rows = [_make_row("2026000001", {"8장": 0.2})]
        config = _make_config()

        label, signals = classify_cause("8장", "학령기", rows, items, config)

        assert label == "기초구멍"

    def test_easy_items_high_rate_yields_미상(self) -> None:
        """hard_share < 0.5 AND mean correct_rate high (>= gap_threshold) → 미상."""
        # Items are easy, but correct_rate is above threshold → no clear cause
        items = [
            _make_item("8장", expected_difficulty="쉬움", correct_rate=0.8),
            _make_item("8장", expected_difficulty="보통", correct_rate=0.75),
        ]
        rows = [_make_row("2026000001", {"8장": 0.8})]
        config = _make_config()

        label, signals = classify_cause("8장", "학령기", rows, items, config)

        assert label == "미상"

    def test_no_items_yields_미상(self) -> None:
        """No items for chapter → 미상."""
        rows = [_make_row("2026000001", {"8장": 0.3})]
        config = _make_config()

        label, signals = classify_cause("8장", "학령기", rows, [], config)

        assert label == "미상"

    def test_signals_contains_required_keys(self) -> None:
        """cause_signals always contains hard_share and item_mean_correct_rate."""
        items = [
            _make_item("8장", expected_difficulty="어려움", correct_rate=0.3),
        ]
        rows = [_make_row("2026000001", {"8장": 0.3})]
        config = _make_config()

        label, signals = classify_cause("8장", "학령기", rows, items, config)

        assert "hard_share" in signals
        assert "item_mean_correct_rate" in signals
        assert "segment_mean_rate" in signals

    def test_signals_hard_share_correct_value(self) -> None:
        """hard_share signal equals proportion of items with expected_difficulty='어려움'."""
        items = [
            _make_item("8장", expected_difficulty="어려움", correct_rate=0.3),
            _make_item("8장", expected_difficulty="보통", correct_rate=0.5),
            _make_item("8장", expected_difficulty="쉬움", correct_rate=0.7),
        ]
        rows = [_make_row("2026000001", {"8장": 0.5})]
        config = _make_config()

        label, signals = classify_cause("8장", "학령기", rows, items, config)

        assert abs(signals["hard_share"] - 1 / 3) < 1e-9

    def test_signals_item_mean_correct_rate_correct(self) -> None:
        """item_mean_correct_rate signal equals mean of item correct_rates."""
        items = [
            _make_item("8장", expected_difficulty="보통", correct_rate=0.4),
            _make_item("8장", expected_difficulty="보통", correct_rate=0.6),
        ]
        rows = [_make_row("2026000001", {"8장": 0.5})]
        config = _make_config()

        label, signals = classify_cause("8장", "학령기", rows, items, config)

        assert abs(signals["item_mean_correct_rate"] - 0.5) < 1e-9

    def test_filters_items_to_chapter(self) -> None:
        """Only items matching the chapter are used; other chapters ignored."""
        items = [
            _make_item("8장", expected_difficulty="어려움", correct_rate=0.3),
            _make_item("9장", expected_difficulty="쉬움", correct_rate=0.9),  # different chapter
        ]
        rows = [_make_row("2026000001", {"8장": 0.3})]
        config = _make_config()

        label, signals = classify_cause("8장", "학령기", rows, items, config)

        # Only 8장 item counted: hard_share = 1.0 → 내용난이도
        assert label == "내용난이도"
        assert abs(signals["hard_share"] - 1.0) < 1e-9

    def test_segment_mean_rate_computed_from_rows(self) -> None:
        """segment_mean_rate signal is mean of chapter rate across segment rows."""
        rows = [
            _make_row("2026000001", {"8장": 0.3}),
            _make_row("2026000002", {"8장": 0.5}),
        ]
        items = [_make_item("8장", expected_difficulty="쉬움", correct_rate=0.3)]
        config = RetroMesterConfig(
            semester="2026-1",
            course_slug="anatomy",
            group_roster={"2026000001": "학령기", "2026000002": "학령기"},
            unit_importance={},
        )

        label, signals = classify_cause("8장", "학령기", rows, items, config)

        assert abs(signals["segment_mean_rate"] - 0.4) < 1e-9
