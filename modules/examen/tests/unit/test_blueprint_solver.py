"""T038 — Unit: blueprint solver chapter-even balance + difficulty + source mix (US3).

TDD (RED phase): tests for select_quiz_subset + solve with quiz slots.

Tests:
- select_quiz_subset: chapter-even, deterministic, stable order
- solve with quiz slots: quiz count matches source_mix, chapter_no set
- whole-exam difficulty distribution from solver
- source mix totals
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import (
    CurriculumEntry,
    CurriculumMap,
    ExamenBlueprint,
    SourceInventoryEntry,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"

_CHAPTERS = [
    "8장 호흡계통",
    "9장 근육계통",
    "10장 소화계통",
]
_CHAPTER_NOS = [8, 9, 10]
_WEEKS = [8, 9, 10]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_curriculum_map(
    chapters: list[str] | None = None,
    chapter_nos: list[int] | None = None,
    weeks: list[int] | None = None,
) -> CurriculumMap:
    chapters = chapters or _CHAPTERS
    chapter_nos = chapter_nos or _CHAPTER_NOS
    weeks = weeks or _WEEKS
    entries = [
        CurriculumEntry(
            week=w,
            chapter=ch,
            chapter_no=no,
            subtopic=None,
            sections=["1. 절"],
        )
        for w, ch, no in zip(weeks, chapters, chapter_nos, strict=False)
    ]
    return CurriculumMap(semester=_SEMESTER, course_slug=_COURSE, entries=entries)


def _make_quiz_entries(
    n: int,
    chapters: list[str] | None = None,
    chapter_nos: list[int] | None = None,
    weeks: list[int] | None = None,
) -> list[SourceInventoryEntry]:
    """Build n synthetic quiz SourceInventoryEntry objects, distributed across chapters."""
    chapters = chapters or _CHAPTERS
    chapter_nos = chapter_nos or _CHAPTER_NOS
    weeks = weeks or _WEEKS
    entries: list[SourceInventoryEntry] = []
    for i in range(n):
        idx = i % len(chapter_nos)
        entries.append(
            SourceInventoryEntry(
                semester=_SEMESTER,
                course_slug=_COURSE,
                source="quiz",
                source_ref=f"퀴즈:{weeks[idx]}주#{i+1}",
                chapter_no=chapter_nos[idx],
                week=weeks[idx],
                stem=f"챕터{chapter_nos[idx]} 문제 {i+1}",
                options=[f"① 보기{i}A", f"② 보기{i}B", f"③ 보기{i}C", f"④ 보기{i}D", f"⑤ 보기{i}E"],
                answer=f"{(i % 5) + 1}",
            )
        )
    return entries


def _make_formative_entries(n: int, chapter_nos: list[int] | None = None) -> list[SourceInventoryEntry]:
    """Build n synthetic formative SourceInventoryEntry objects."""
    chapter_nos = chapter_nos or _CHAPTER_NOS
    entries: list[SourceInventoryEntry] = []
    for i in range(n):
        ch_no = chapter_nos[i % len(chapter_nos)]
        entries.append(
            SourceInventoryEntry(
                semester=_SEMESTER,
                course_slug=_COURSE,
                source="formative",
                source_ref=f"형성평가:{ch_no}장#{i+1}",
                chapter_no=ch_no,
                week=ch_no,
                stem=f"형성평가 질문 {i+1}",
                model_answer="모범답안",
                keywords=[],
                rubric={"high": "h", "mid": "m", "low": "l"},
            )
        )
    return entries


# ---------------------------------------------------------------------------
# select_quiz_subset tests
# ---------------------------------------------------------------------------


class TestSelectQuizSubset:
    """Unit tests for select_quiz_subset (T043 helper)."""

    def test_selects_target_count(self) -> None:
        """select_quiz_subset returns exactly target items."""
        from examen.plan.blueprint import select_quiz_subset

        inventory = _make_quiz_entries(30)
        chapters = _CHAPTER_NOS
        result = select_quiz_subset(inventory, target=15, chapters=chapters)
        assert len(result) == 15, f"Expected 15, got {len(result)}"

    def test_chapter_even_distribution(self) -> None:
        """Chapter counts differ by at most 1 (chapter-even selection)."""
        from collections import Counter

        from examen.plan.blueprint import select_quiz_subset

        inventory = _make_quiz_entries(30)
        result = select_quiz_subset(inventory, target=15, chapters=_CHAPTER_NOS)
        counts = list(Counter(e.chapter_no for e in result).values())
        assert max(counts) - min(counts) <= 1, (
            f"Chapter distribution not even: {counts}"
        )

    def test_all_chapters_represented(self) -> None:
        """All chapters appear in the subset when inventory has enough items."""
        from examen.plan.blueprint import select_quiz_subset

        inventory = _make_quiz_entries(30)
        result = select_quiz_subset(inventory, target=15, chapters=_CHAPTER_NOS)
        selected_chapters = {e.chapter_no for e in result}
        for ch in _CHAPTER_NOS:
            assert ch in selected_chapters, f"Chapter {ch} missing from selection"

    def test_deterministic_stable_order(self) -> None:
        """Calling select_quiz_subset twice with same args returns identical lists."""
        from examen.plan.blueprint import select_quiz_subset

        inventory = _make_quiz_entries(30)
        r1 = select_quiz_subset(inventory, target=15, chapters=_CHAPTER_NOS)
        r2 = select_quiz_subset(inventory, target=15, chapters=_CHAPTER_NOS)
        assert [e.source_ref for e in r1] == [e.source_ref for e in r2], (
            "select_quiz_subset is not deterministic"
        )

    def test_target_2_returns_correct_count(self) -> None:
        """target=2 with 3 chapters returns exactly 2 items (chapter-even might give 1+1+0)."""
        from examen.plan.blueprint import select_quiz_subset

        inventory = _make_quiz_entries(9)  # 3 per chapter
        result = select_quiz_subset(inventory, target=2, chapters=_CHAPTER_NOS)
        # With 3 chapters and target 2: 2 chapters get 1, 1 chapter gets 0
        # OR all 3 chapters get their proportional share, final count = 2
        # The exact distribution doesn't matter as long as total = target
        assert len(result) == 2, f"Expected 2 items, got {len(result)}"

    def test_target_equals_inventory_size(self) -> None:
        """When target == len(inventory), all items are selected."""
        from examen.plan.blueprint import select_quiz_subset

        inventory = _make_quiz_entries(15)
        result = select_quiz_subset(inventory, target=15, chapters=_CHAPTER_NOS)
        assert len(result) == 15

    def test_raises_if_insufficient_inventory(self) -> None:
        """Raises ValueError if inventory has fewer items than target (after chapter-even)."""
        from examen.plan.blueprint import select_quiz_subset

        inventory = _make_quiz_entries(3)  # only 3 items, 1 per chapter
        with pytest.raises(ValueError, match="quiz"):
            select_quiz_subset(inventory, target=15, chapters=_CHAPTER_NOS)

    def test_empty_inventory_raises(self) -> None:
        """Empty inventory raises ValueError."""
        from examen.plan.blueprint import select_quiz_subset

        with pytest.raises(ValueError, match="quiz"):
            select_quiz_subset([], target=5, chapters=_CHAPTER_NOS)

    def test_subset_items_are_from_inventory(self) -> None:
        """All selected items are from the original inventory (no fabrication)."""
        from examen.plan.blueprint import select_quiz_subset

        inventory = _make_quiz_entries(30)
        inventory_refs = {e.source_ref for e in inventory}
        result = select_quiz_subset(inventory, target=15, chapters=_CHAPTER_NOS)
        for entry in result:
            assert entry.source_ref in inventory_refs, (
                f"Selected entry {entry.source_ref!r} not in original inventory"
            )

    def test_no_duplicates_in_subset(self) -> None:
        """No source_ref appears twice in the selected subset."""
        from examen.plan.blueprint import select_quiz_subset

        inventory = _make_quiz_entries(30)
        result = select_quiz_subset(inventory, target=15, chapters=_CHAPTER_NOS)
        refs = [e.source_ref for e in result]
        assert len(refs) == len(set(refs)), "Duplicate entries in quiz subset"


# ---------------------------------------------------------------------------
# solve() with quiz slots
# ---------------------------------------------------------------------------


class TestSolveWithQuizSlots:
    """solve() correctly generates quiz slots when source_mix includes quiz."""

    def test_solve_returns_correct_quiz_count(self) -> None:
        """solve() returns exactly source_mix['quiz'] slots with source='quiz'."""
        from examen.plan.blueprint import solve

        # total_items must be 40-50; use 40 = 22 textbook + 9 formative + 9 quiz
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=40,
            chapters=_CHAPTERS,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": 22, "formative": 9, "quiz": 9},
        )
        formative = _make_formative_entries(9)
        curriculum_map = _make_curriculum_map()
        slots = solve(blueprint, curriculum_map, formative_inventory=formative)

        quiz_slots = [s for s in slots if s.source == "quiz"]
        assert len(quiz_slots) == 9, f"Expected 9 quiz slots, got {len(quiz_slots)}"

    def test_quiz_slots_have_chapter_no(self) -> None:
        """All quiz slots have chapter_no set (not 0 for known chapters)."""
        from examen.plan.blueprint import solve

        # 40 = 22 textbook + 12 formative + 6 quiz
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=40,
            chapters=_CHAPTERS,
            difficulty_targets={"easy": 0.50, "medium": 0.50, "hard": 0.0},
            source_mix={"textbook": 22, "formative": 12, "quiz": 6},
        )
        formative = _make_formative_entries(12)
        curriculum_map = _make_curriculum_map()
        slots = solve(blueprint, curriculum_map, formative_inventory=formative)
        for slot in slots:
            if slot.source == "quiz":
                assert slot.chapter_no != 0, (
                    f"Quiz slot {slot.slot_id} has chapter_no=0 (unresolved chapter)"
                )

    def test_solve_total_slots_equals_total_items(self) -> None:
        """solve() returns exactly blueprint.total_items slots."""
        from examen.plan.blueprint import solve

        # 40 = 22 textbook + 9 formative + 9 quiz
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=40,
            chapters=_CHAPTERS,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": 22, "formative": 9, "quiz": 9},
        )
        formative = _make_formative_entries(9)
        curriculum_map = _make_curriculum_map()
        slots = solve(blueprint, curriculum_map, formative_inventory=formative)
        assert len(slots) == 40, f"Expected 40 slots, got {len(slots)}"

    def test_difficulty_distribution_whole_exam(self) -> None:
        """Whole-exam difficulty distribution ≈ 45/35/20 (±5%)."""
        from collections import Counter

        from examen.plan.blueprint import solve

        # 40 = 22 textbook + 9 formative + 9 quiz
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=40,
            chapters=_CHAPTERS,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": 22, "formative": 9, "quiz": 9},
        )
        formative = _make_formative_entries(9)
        curriculum_map = _make_curriculum_map()
        slots = solve(blueprint, curriculum_map, formative_inventory=formative)

        counts = Counter(s.difficulty for s in slots)
        total = len(slots)
        easy_frac = counts["1_쉬움"] / total
        medium_frac = counts["2_보통"] / total
        hard_frac = counts["3_어려움"] / total
        assert abs(easy_frac - 0.45) < 0.06, f"Easy {easy_frac:.2f} != ~0.45"
        assert abs(medium_frac - 0.35) < 0.06, f"Medium {medium_frac:.2f} != ~0.35"
        assert abs(hard_frac - 0.20) < 0.06, f"Hard {hard_frac:.2f} != ~0.20"

    def test_chapter_even_across_all_sources(self) -> None:
        """Chapter-even: max chapter count - min ≤ 1 for all slots."""
        from collections import Counter

        from examen.plan.blueprint import solve

        # 42 = 24 textbook + 9 formative + 9 quiz (divisible by 3 chapters)
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=42,
            chapters=_CHAPTERS,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": 24, "formative": 9, "quiz": 9},
        )
        formative = _make_formative_entries(9)
        curriculum_map = _make_curriculum_map()
        slots = solve(blueprint, curriculum_map, formative_inventory=formative)

        counts = list(Counter(s.chapter_no for s in slots).values())
        assert max(counts) - min(counts) <= 1, (
            f"Chapter distribution not even: {counts}"
        )

    def test_source_mix_totals_match(self) -> None:
        """Source counts in slots exactly match source_mix declaration."""
        from collections import Counter

        from examen.plan.blueprint import solve

        n_textbook, n_formative, n_quiz = 22, 9, 9  # sum = 40
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=40,
            chapters=_CHAPTERS,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": n_textbook, "formative": n_formative, "quiz": n_quiz},
        )
        formative = _make_formative_entries(n_formative)
        curriculum_map = _make_curriculum_map()
        slots = solve(blueprint, curriculum_map, formative_inventory=formative)

        counts = Counter(s.source for s in slots)
        assert counts["textbook"] == n_textbook
        assert counts["formative"] == n_formative
        assert counts["quiz"] == n_quiz

    def test_textbook_light_unrealizable_mix_fails_loud(self) -> None:
        """T064 regression: a textbook-light mix that can't be realized chapter-evenly
        must raise a located ValueError instead of silently dropping quiz/formative slots.

        Adversary repro: 4 chapters, total=40, source_mix={textbook:1, formative:6,
        quiz:33}.  Per-chapter integer distribution over-fills chapter 0
        (formative2+quiz9+textbook1=12 > 10), and the old code truncated — silently
        replacing a declared quiz slot with a phantom textbook slot.  The solver must
        now surface this as a fail-fast (헌장: 조용한 누락 금지).
        """
        from examen.plan.blueprint import solve

        chapters = ["8장 호흡계통", "9장 근육계통", "10장 소화계통", "11장 순환계통"]
        chapter_nos = [8, 9, 10, 11]
        weeks = [8, 9, 10, 11]
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=40,
            chapters=chapters,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": 1, "formative": 6, "quiz": 33},
        )
        curriculum_map = _make_curriculum_map(
            chapters=chapters, chapter_nos=chapter_nos, weeks=weeks
        )
        with pytest.raises(ValueError, match="챕터-균등으로 실현할 수 없습니다"):
            solve(blueprint, curriculum_map)

    def test_typical_textbook_heavy_mix_is_realized(self) -> None:
        """The typical operating range (textbook fills the rest) realizes exactly —
        the new fail-fast must NOT fire for normal blueprints."""
        from collections import Counter

        from examen.plan.blueprint import solve

        chapters = ["8장 호흡계통", "9장 근육계통", "10장 소화계통", "11장 순환계통"]
        chapter_nos = [8, 9, 10, 11]
        weeks = [8, 9, 10, 11]
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=40,
            chapters=chapters,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": 13, "formative": 12, "quiz": 15},
        )
        curriculum_map = _make_curriculum_map(
            chapters=chapters, chapter_nos=chapter_nos, weeks=weeks
        )
        slots = solve(blueprint, curriculum_map)
        counts = Counter(s.source for s in slots)
        assert counts["textbook"] == 13
        assert counts["formative"] == 12
        assert counts["quiz"] == 15


class TestSolveFormativeChapterDistribution:
    """전수 형성평가 슬롯의 장 분포는 인벤토리의 실제 장 분포를 따라야 한다.

    형성평가는 실제 출제된 문항을 전수 포함하므로 각 문항의 장은 고정 데이터다.
    솔버가 형성 슬롯을 챕터-균등으로 강제하면 pipeline 의 위치 기반(chapter-major)
    형성 슬롯↔인벤토리 교차검증이 불균등 인벤토리에서 어긋난다.  따라서 솔버는
    형성 슬롯 장 분포를 인벤토리에서 도출해야 한다.
    """

    def test_formative_slots_follow_inventory_chapter_counts(self) -> None:
        from collections import Counter

        from examen.plan.blueprint import solve

        # 불균등 인벤토리: 10장에 형성 5개, 8·9장에 각 2개 (챕터-균등이 아님).
        formative = (
            _make_formative_entries(2, chapter_nos=[8])
            + _make_formative_entries(2, chapter_nos=[9])
            + _make_formative_entries(5, chapter_nos=[10])
        )
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=42,
            chapters=_CHAPTERS,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": 33, "formative": 9, "quiz": 0},
        )
        curriculum_map = _make_curriculum_map()
        slots = solve(blueprint, curriculum_map, formative_inventory=formative)

        fcounts = Counter(s.chapter_no for s in slots if s.source == "formative")
        assert fcounts[8] == 2
        assert fcounts[9] == 2
        assert fcounts[10] == 5

    def test_formative_slot_order_matches_sorted_inventory(self) -> None:
        """슬롯 순서(chapter-major)의 형성 장 시퀀스 == 장 오름차순 인벤토리 시퀀스.

        이것이 pipeline 위치 기반 교차검증의 통과 조건이다.
        """
        from examen.plan.blueprint import solve

        formative = (
            _make_formative_entries(2, chapter_nos=[8])
            + _make_formative_entries(2, chapter_nos=[9])
            + _make_formative_entries(5, chapter_nos=[10])
        )
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="기말고사",
            total_items=42,
            chapters=_CHAPTERS,
            difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
            source_mix={"textbook": 33, "formative": 9, "quiz": 0},
        )
        curriculum_map = _make_curriculum_map()
        slots = solve(blueprint, curriculum_map, formative_inventory=formative)

        slot_seq = [s.chapter_no for s in slots if s.source == "formative"]
        inv_seq = sorted(e.chapter_no for e in formative)
        assert slot_seq == inv_seq
