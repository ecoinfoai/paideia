"""T045 — Unit tests for align/alignment.py (build_alignment).

RED phase: all tests must fail until align/alignment.py is implemented.

Alignment flag rules (authoritative spec):
- 인지수준절벽: chapter has any entry in the cliff dict (from detect_cliff).
- 과소교수-과다평가: tested_items share > taught_weeks share by > SHARE_MARGIN (0.10)
  AND taught_weeks < median_taught_weeks (i.e., under-taught chapter).
  More precisely:
    tested_share = tested_items / total_tested_items
    taught_share = taught_weeks / total_taught_weeks
    flag if (tested_share - taught_share) > SHARE_MARGIN
- 과다교수-과소평가: taught_share - tested_share > SHARE_MARGIN (over-taught, under-tested)
- Flag priority: 인지수준절벽 > 과소교수-과다평가 > 과다교수-과소평가 > 정렬됨
- 기대-실제괴리 is not assigned by build_alignment (reserved for item-difficulty mismatch,
  outside this function's scope). It is NOT emitted here.
"""

from __future__ import annotations

import json

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    ExamenBlueprint,
    ItemStatistics,
    RetroMesterConfig,
)
from paideia_shared.schemas.curriculum_map import CurriculumEntry, CurriculumMap


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


def _make_config(cliff_drop: float = 0.15) -> RetroMesterConfig:
    return RetroMesterConfig(
        semester="2026-1",
        course_slug="anatomy",
        group_roster={"2026000001": "학령기", "2026000002": "만학도"},
        unit_importance={"1장": "상", "2장": "중"},
        gap_threshold=0.6,
        cognitive_cliff_drop=cliff_drop,
    )


def _make_row(student_id: str, chapter_rates: dict[str, float]) -> CombinedAnalysisRow:
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
        chapter_correct_rates=chapter_rates,
        source_correct_rates={"형성평가": 0.5},
        difficulty_correct_rates={1: 0.7, 2: 0.5, 3: 0.3},
        expected_difficulty_correct_rates={"쉬움": 0.7, "보통": 0.5, "어려움": 0.3},
        item_type_correct_rates={"지식축적": 0.6, "이해": 0.5},
        interest_chapters_correct_rate=None,
        aversion_chapters_correct_rate=None,
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


def _make_item(
    item_no: int,
    chapter: str,
    item_type: str = "지식축적",
    correct_rate: float = 0.70,
) -> ItemStatistics:
    cr = correct_rate
    # Ensure option_distribution sums to ~1.0
    remainder = round(1.0 - cr, 4)
    each = round(remainder / 4, 4)
    dist = {1: cr, 2: each, 3: each, 4: each, 5: round(remainder - 3 * each, 4)}
    return ItemStatistics(
        item_no=item_no,
        semester="2026-1",
        course_slug="anatomy",
        chapter=chapter,
        week=None,
        item_type=item_type,
        difficulty_level=3,
        expected_difficulty="보통",
        source="형성평가",
        correct_answer=1,
        n_responders=20,
        n_correct=round(cr * 20),
        n_omit=0,
        correct_rate=cr,
        omit_rate=0.0,
        discrimination_index=0.25,
        point_biserial=0.35,
        top_distractor_no=2,
        top_distractor_rate=0.20,
        is_top_distractor_adjacent=False,
        option_distribution=dist,
        distractor_label="특이사항 없음",
    )


def _make_curriculum(
    entries: list[tuple[int, str, int]],
) -> CurriculumMap:
    """entries: list of (week, chapter, chapter_no)."""
    return CurriculumMap(
        semester="2026-1",
        course_slug="anatomy",
        entries=[
            CurriculumEntry(week=w, chapter=c, chapter_no=cn, subtopic=None, sections=["s"])
            for w, c, cn in entries
        ],
    )


def _make_blueprint(chapters: list[str], total_items: int = 40) -> ExamenBlueprint:
    per = total_items // len(chapters)
    return ExamenBlueprint(
        semester="2026-1",
        course_slug="anatomy",
        exam_name="기말",
        total_items=total_items,
        chapters=chapters,
        difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
        source_mix={"formative": per, "quiz": per, "textbook": total_items - 2 * per},
        quiz_target=per,
        answer_key_balance=True,
    )


# ---------------------------------------------------------------------------
# Tests for AlignmentFinding flags
# ---------------------------------------------------------------------------


class TestBuildAlignmentFlags:
    """Tests for build_alignment() flag assignment."""

    def test_정렬됨_when_balanced(self) -> None:
        """Chapter taught and tested proportionally → 정렬됨."""
        from retro_mester.align.alignment import build_alignment

        rows = [
            _make_row("2026000001", {"1장": 0.70, "2장": 0.65}),
            _make_row("2026000002", {"1장": 0.72, "2장": 0.68}),
        ]
        items = [
            _make_item(1, "1장"),
            _make_item(2, "2장"),
        ]
        curriculum = _make_curriculum([(1, "1장", 1), (2, "2장", 2)])
        blueprint = _make_blueprint(["1장", "2장"], total_items=40)
        config = _make_config()

        findings = build_alignment(items, curriculum, blueprint, rows, config)
        flags = {f.chapter: f.flag for f in findings}

        # With equal share on both sides, expect 정렬됨 for all
        for chapter in ["1장", "2장"]:
            assert flags.get(chapter) == "정렬됨", f"Expected 정렬됨 for {chapter}, got {flags.get(chapter)}"

    def test_인지수준절벽_when_cliff(self) -> None:
        """Chapter with a cognitive cliff → 인지수준절벽 flag."""
        from retro_mester.align.alignment import build_alignment

        rows = [
            _make_row("2026000001", {"1장": 0.65}),
            _make_row("2026000002", {"1장": 0.60}),
        ]
        # 지식축적 high, 이해 low → cliff
        items = [
            _make_item(1, "1장", "지식축적", 0.85),
            _make_item(2, "1장", "이해", 0.55),   # 0.85 - 0.55 = 0.30 > 0.15
        ]
        curriculum = _make_curriculum([(1, "1장", 1)])
        blueprint = _make_blueprint(["1장"], total_items=40)
        config = _make_config(cliff_drop=0.15)

        findings = build_alignment(items, curriculum, blueprint, rows, config)
        flags = {f.chapter: f.flag for f in findings}
        assert flags.get("1장") == "인지수준절벽"

    def test_과소교수_과다평가_when_under_taught(self) -> None:
        """Chapter taught 1 week but holds disproportionate test share → 과소교수-과다평가."""
        from retro_mester.align.alignment import build_alignment

        rows = [
            _make_row("2026000001", {"1장": 0.60, "2장": 0.62}),
            _make_row("2026000002", {"1장": 0.58, "2장": 0.64}),
        ]
        # 1장 gets 1 week but many items; 2장 gets 3 weeks but few items
        items = (
            [_make_item(i, "1장") for i in range(1, 11)]   # 10 items for 1장
            + [_make_item(i + 10, "2장") for i in range(1, 3)]  # 2 items for 2장
        )
        curriculum = _make_curriculum([
            (1, "1장", 1),       # 1 week
            (2, "2장", 2),       # 3 weeks
            (3, "2장", 2),
            (4, "2장", 2),
        ])
        blueprint = _make_blueprint(["1장", "2장"], total_items=40)
        config = _make_config()

        findings = build_alignment(items, curriculum, blueprint, rows, config)
        flags = {f.chapter: f.flag for f in findings}
        # 1장: tested_share = 10/12 ≈ 0.83, taught_share = 1/4 = 0.25
        # 0.83 - 0.25 = 0.58 > 0.10 → 과소교수-과다평가
        assert flags.get("1장") == "과소교수-과다평가"

    def test_cognitive_profile_in_finding(self) -> None:
        """cognitive_profile contains item_type rates for the chapter."""
        from retro_mester.align.alignment import build_alignment

        rows = [
            _make_row("2026000001", {"1장": 0.70}),
        ]
        items = [
            _make_item(1, "1장", "지식축적", 0.80),
            _make_item(2, "1장", "이해", 0.60),
        ]
        curriculum = _make_curriculum([(1, "1장", 1)])
        blueprint = _make_blueprint(["1장"], total_items=40)
        config = _make_config()

        findings = build_alignment(items, curriculum, blueprint, rows, config)
        assert len(findings) >= 1
        f = next(x for x in findings if x.chapter == "1장")
        assert "지식축적" in f.cognitive_profile
        assert "이해" in f.cognitive_profile

    def test_taught_weeks_correct(self) -> None:
        """taught_weeks = count of curriculum entries for chapter."""
        from retro_mester.align.alignment import build_alignment

        rows = [
            _make_row("2026000001", {"1장": 0.70}),
        ]
        items = [_make_item(1, "1장")]
        curriculum = _make_curriculum([(1, "1장", 1), (2, "1장", 1)])  # 2 weeks
        blueprint = _make_blueprint(["1장"], total_items=40)
        config = _make_config()

        findings = build_alignment(items, curriculum, blueprint, rows, config)
        f = next(x for x in findings if x.chapter == "1장")
        assert f.taught_weeks == 2

    def test_tested_items_correct(self) -> None:
        """tested_items = count of ItemStatistics rows for chapter."""
        from retro_mester.align.alignment import build_alignment

        rows = [_make_row("2026000001", {"1장": 0.70})]
        items = [_make_item(1, "1장"), _make_item(2, "1장"), _make_item(3, "1장")]
        curriculum = _make_curriculum([(1, "1장", 1)])
        blueprint = _make_blueprint(["1장"], total_items=40)
        config = _make_config()

        findings = build_alignment(items, curriculum, blueprint, rows, config)
        f = next(x for x in findings if x.chapter == "1장")
        assert f.tested_items == 3

    def test_learned_rate_is_cohort_mean(self) -> None:
        """learned_rate = cohort mean of chapter correct_rate."""
        from retro_mester.align.alignment import build_alignment

        rows = [
            _make_row("2026000001", {"1장": 0.60}),
            _make_row("2026000002", {"1장": 0.80}),
        ]
        items = [_make_item(1, "1장")]
        curriculum = _make_curriculum([(1, "1장", 1)])
        blueprint = _make_blueprint(["1장"], total_items=40)
        config = _make_config()

        findings = build_alignment(items, curriculum, blueprint, rows, config)
        f = next(x for x in findings if x.chapter == "1장")
        assert abs(f.learned_rate - 0.70) < 1e-9

    def test_cliff_priority_over_under_taught(self) -> None:
        """인지수준절벽 takes priority over 과소교수-과다평가 when both conditions met."""
        from retro_mester.align.alignment import build_alignment

        rows = [_make_row("2026000001", {"1장": 0.70})]
        # Many items (would trigger 과소교수-과다평가) AND cliff exists
        items = (
            [_make_item(1, "1장", "지식축적", 0.85)]
            + [_make_item(i, "1장", "이해", 0.50) for i in range(2, 11)]
        )
        curriculum = _make_curriculum([(1, "1장", 1), (2, "2장", 2), (3, "2장", 2), (4, "2장", 2)])
        blueprint = _make_blueprint(["1장", "2장"], total_items=40)
        config = _make_config(cliff_drop=0.15)

        findings = build_alignment(items, curriculum, blueprint, rows, config)
        flags = {f.chapter: f.flag for f in findings}
        # Cliff takes priority
        assert flags.get("1장") == "인지수준절벽"

    def test_one_finding_per_chapter(self) -> None:
        """build_alignment returns exactly one AlignmentFinding per chapter."""
        from retro_mester.align.alignment import build_alignment

        rows = [_make_row("2026000001", {"1장": 0.70, "2장": 0.65})]
        items = [_make_item(1, "1장"), _make_item(2, "2장")]
        curriculum = _make_curriculum([(1, "1장", 1), (2, "2장", 2)])
        blueprint = _make_blueprint(["1장", "2장"], total_items=40)
        config = _make_config()

        findings = build_alignment(items, curriculum, blueprint, rows, config)
        chapters = [f.chapter for f in findings]
        assert len(chapters) == len(set(chapters)), "Duplicate chapter findings"
