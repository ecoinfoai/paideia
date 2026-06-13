"""Unit tests for maieutica.plan.slots — T023.

TDD: failing tests written BEFORE implementation (RED → GREEN).

Covers:
- spec(quiz_count=N, formative_count=M, week=W, chapter_no=C) → exactly N
  quiz slots `quiz-W-001..` + M formative slots `formative-C-001..`.
- 1-based, zero-padded (3-digit) ordinals.
- Deterministic ordering: quiz slots first (ascending), then formative slots.
"""

from __future__ import annotations

from paideia_shared.schemas import MaieuticaGenerationSpec


def _spec(quiz: int, formative: int, week: int = 3, chapter_no: int = 8):
    return MaieuticaGenerationSpec(
        semester="2026-1",
        course_slug="anatomy",
        week=week,
        chapter_no=chapter_no,
        chapter="8장 호흡계통",
        quiz_count=quiz,
        formative_count=formative,
    )


class TestPlanSlots:
    def test_counts_match_spec(self) -> None:
        from maieutica.plan.slots import plan_slots

        slots = plan_slots(_spec(quiz=20, formative=3))
        quiz = [s for s in slots if s.kind == "quiz"]
        formative = [s for s in slots if s.kind == "formative"]
        assert len(quiz) == 20
        assert len(formative) == 3

    def test_quiz_slot_ids(self) -> None:
        from maieutica.plan.slots import plan_slots

        slots = plan_slots(_spec(quiz=3, formative=2, week=5))
        quiz_ids = [s.slot_id for s in slots if s.kind == "quiz"]
        assert quiz_ids == ["quiz-5-001", "quiz-5-002", "quiz-5-003"]

    def test_formative_slot_ids(self) -> None:
        from maieutica.plan.slots import plan_slots

        slots = plan_slots(_spec(quiz=1, formative=3, chapter_no=12))
        formative_ids = [s.slot_id for s in slots if s.kind == "formative"]
        assert formative_ids == [
            "formative-12-001",
            "formative-12-002",
            "formative-12-003",
        ]

    def test_ordering_quiz_then_formative(self) -> None:
        from maieutica.plan.slots import plan_slots

        slots = plan_slots(_spec(quiz=2, formative=2))
        kinds = [s.kind for s in slots]
        assert kinds == ["quiz", "quiz", "formative", "formative"]

    def test_deterministic(self) -> None:
        from maieutica.plan.slots import plan_slots

        spec = _spec(quiz=4, formative=2)
        a = [(s.slot_id, s.kind) for s in plan_slots(spec)]
        b = [(s.slot_id, s.kind) for s in plan_slots(spec)]
        assert a == b

    def test_slot_carries_week_and_chapter(self) -> None:
        from maieutica.plan.slots import plan_slots

        slots = plan_slots(_spec(quiz=1, formative=1, week=7, chapter_no=9))
        quiz = next(s for s in slots if s.kind == "quiz")
        formative = next(s for s in slots if s.kind == "formative")
        assert quiz.week == 7
        assert quiz.chapter_no == 9
        assert quiz.ordinal == 1
        assert formative.ordinal == 1
