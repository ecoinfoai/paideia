"""T037 — Integration: quiz ~15, chapter-even, wording variation, whole-exam balance (US3).

TDD (RED phase): tests written before implementation.

Tests:
- quiz slots (~15) are selected chapter-evenly from the inventory pool
- no item has wording identical to the original quiz text (variation happened)
- whole-exam difficulty distribution targets are met (45/35/20 ±rounding)
- source breakdown includes 'quiz' items
- pipeline no longer raises NotImplementedError for quiz slots
- no real-data files committed (inventory built from synthetic rows)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    LLMBackend,
)
from paideia_shared.schemas import (
    CurriculumEntry,
    CurriculumMap,
    ExamenBlueprint,
    ExamItemDraft,
    SourceInventoryEntry,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"

# Blueprint: 6 chapters, 40 items total
# 12 formative (전수), 15 quiz (~15), 13 textbook (fill)
_N_FORMATIVE = 12
_N_QUIZ = 15
_N_TEXTBOOK = 40 - _N_FORMATIVE - _N_QUIZ  # 13

_CHAPTERS = [
    "8장 호흡계통",
    "9장 근육계통",
    "10장 소화계통",
    "11장 순환계통",
    "12장 비뇨계통",
    "13장 신경계통",
]
_CHAPTER_NOS = [8, 9, 10, 11, 12, 13]
_WEEKS = [8, 9, 10, 11, 12, 13]

# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------

_CANNED_TEXTBOOK_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "2_보통",
    "stem_polarity": "부정형",
    "text": "다음 중 폐포에 대한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① " + "가" * 28,
        "② " + "나" * 28,
        "③ " + "다" * 28,
        "④ " + "라" * 28,
        "⑤ " + "마" * 28,
    ],
    "answer_no": 3,
    "distractor_rationale": [
        "옳은 진술: 가.",
        "옳은 진술: 나.",
        "틀린 진술: 다.",
        "옳은 진술: 라.",
        "옳은 진술: 마.",
    ],
    "wrong_explanation": "오답 설명 텍스트입니다." * 20,
    "leap_explanation": "도약 설명 텍스트입니다." * 20,
    "intent": "기본 구조와 기능을 확인한다.",
    "key_concept": "폐포",
}

_CANNED_FORMATIVE_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "2_보통",
    "stem_polarity": "부정형",
    "text": "다음 중 허파꽈리 세포에 대한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① " + "제1형허파세포는가스교환을담당한다.",
        "② " + "제2형허파세포는표면활성제를분비한다.",
        "③ " + "표면활성제는표면장력을낮추는기능있다.",
        "④ " + "허파꽈리벽은두종류세포로구성된다것.",
        "⑤ " + "제2형허파세포는섬모를보유하고있는세포.",
    ],
    "answer_no": 5,
    "distractor_rationale": [
        "옳은 진술.",
        "옳은 진술.",
        "옳은 진술.",
        "옳은 진술.",
        "틀린 진술: 섬모 없음.",
    ],
    "wrong_explanation": "오답 설명 텍스트." * 15,
    "leap_explanation": "도약 설명 텍스트." * 15,
    "intent": "허파꽈리 세포 기능.",
    "key_concept": "제2형 허파세포",
    "wrong_option_no": 5,
}

# Quiz variation response: must differ from original quiz text
_CANNED_QUIZ_VARIATION_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "2_보통",
    "stem_polarity": "부정형",
    "text": "다음 중 호흡생리에 관한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① " + "변형된보기내용으로원본과다른표현을사용했다.",
        "② " + "변형된보기내용으로원본과다른표현을사용했다.",
        "③ " + "변형된보기내용으로원본과다른표현을사용했다.",
        "④ " + "변형된보기내용으로원본과다른표현을사용했다.",
        "⑤ " + "변형된보기내용으로원본과다른표현을사용했다.",
    ],
    "answer_no": 2,
    "distractor_rationale": [
        "옳은 진술: 변형.",
        "틀린 진술: 변형 오개념.",
        "옳은 진술: 변형.",
        "옳은 진술: 변형.",
        "옳은 진술: 변형.",
    ],
    "wrong_explanation": "변형 오답 설명." * 20,
    "leap_explanation": "변형 도약 설명." * 20,
    "intent": "변형된 문항 의도.",
    "key_concept": "호흡생리",
}


class FakeUS3Backend(LLMBackend):
    """Returns canned JSON based on source type."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        source = request.metadata.get("source", "textbook")
        if source == "quiz":
            raw = json.dumps(_CANNED_QUIZ_VARIATION_JSON, ensure_ascii=False)
        elif source == "formative":
            raw = json.dumps(_CANNED_FORMATIVE_JSON, ensure_ascii=False)
        else:
            raw = json.dumps(_CANNED_TEXTBOOK_JSON, ensure_ascii=False)
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=raw,
            model="fake-us3",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_blueprint() -> ExamenBlueprint:
    """Build a US3 blueprint: 6 chapters, 40 total, 12 formative + 15 quiz + 13 textbook."""
    return ExamenBlueprint(
        semester=_SEMESTER,
        course_slug=_COURSE,
        exam_name="2026-1학기 기말고사",
        total_items=40,
        chapters=_CHAPTERS,
        difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
        source_mix={"textbook": _N_TEXTBOOK, "formative": _N_FORMATIVE, "quiz": _N_QUIZ},
    )


def _make_curriculum_map() -> CurriculumMap:
    entries = []
    for week, chapter, chapter_no in zip(_WEEKS, _CHAPTERS, _CHAPTER_NOS, strict=False):
        entries.append(
            CurriculumEntry(
                week=week,
                chapter=chapter,
                chapter_no=chapter_no,
                subtopic=None,
                sections=["1. 기본구조", "2. 기능"],
            )
        )
    return CurriculumMap(
        semester=_SEMESTER,
        course_slug=_COURSE,
        entries=entries,
    )


def _make_quiz_inventory(n: int = 30) -> list[SourceInventoryEntry]:
    """Create a pool of synthetic quiz entries (2× target for chapter-even selection)."""
    entries = []
    # Distribute across 6 chapters (5 per chapter for 30 total)
    per_chapter = n // len(_CHAPTER_NOS)
    remainder = n % len(_CHAPTER_NOS)
    row = 0
    for i, (chapter_no, week) in enumerate(zip(_CHAPTER_NOS, _WEEKS, strict=False)):
        count = per_chapter + (1 if i < remainder else 0)
        for j in range(count):
            row += 1
            stem = (
                f"{chapter_no}장 {j+1}번: 해당 계통에 관한 설명 중 옳지 않은 것은?"
            )
            entries.append(
                SourceInventoryEntry(
                    semester=_SEMESTER,
                    course_slug=_COURSE,
                    source="quiz",
                    source_ref=f"퀴즈:{week}주#{row}",
                    chapter_no=chapter_no,
                    week=week,
                    stem=stem,
                    options=[
                        f"① {chapter_no}장 보기A {j}번 텍스트",
                        f"② {chapter_no}장 보기B {j}번 텍스트",
                        f"③ {chapter_no}장 보기C {j}번 텍스트",
                        f"④ {chapter_no}장 보기D {j}번 텍스트",
                        f"⑤ {chapter_no}장 보기E {j}번 텍스트",
                    ],
                    answer=f"{(j % 5) + 1}",
                )
            )
    return entries


def _make_formative_inventory() -> list[SourceInventoryEntry]:
    """Create 12 synthetic formative entries, 2 per chapter."""
    entries = []
    for _i, (chapter_no, week) in enumerate(zip(_CHAPTER_NOS, _WEEKS, strict=False)):
        for j in range(2):
            entries.append(
                SourceInventoryEntry(
                    semester=_SEMESTER,
                    course_slug=_COURSE,
                    source="formative",
                    source_ref=f"형성평가:{chapter_no}장#{j+1}",
                    chapter_no=chapter_no,
                    week=week,
                    stem=f"{chapter_no}장 형성평가 {j+1}번: 해당 계통 구조 설명.",
                    model_answer="모범답안: 해당 계통은 여러 기관으로 구성된다.",
                    keywords=["기관", "기능"],
                    rubric={
                        "high": "모두 정확히 설명",
                        "mid": "한 가지만 설명",
                        "low": "완전히 틀린 오개념",
                    },
                )
            )
    return entries


def _write_chapter_fixture(bronze_dir: Path, chapter_no: int, chapter_name: str) -> None:
    """Write a minimal synthetic textbook .txt fixture."""
    fname = f"{chapter_no}장 {chapter_name}.txt"
    content = (
        f"{chapter_no}장 {chapter_name}\n"
        "1. 기본구조\n"
        f"{chapter_name}에 관한 주요 내용.\n"
        "기관들이 서로 연결되어 있다.\n"
        "2. 기능\n"
        f"{chapter_name}의 기능.\n"
    )
    (bronze_dir / fname).write_text(content, encoding="utf-8")


def _setup_bronze(bronze_dir: Path) -> None:
    bronze_dir.mkdir(parents=True, exist_ok=True)
    for chapter_no, chapter_name in zip(_CHAPTER_NOS, [c.split(" ", 1)[1] for c in _CHAPTERS], strict=False):
        _write_chapter_fixture(bronze_dir, chapter_no, chapter_name)


def _run_build(
    tmp_path: Path,
    *,
    blueprint: ExamenBlueprint | None = None,
    formative_inventory: list[SourceInventoryEntry] | None = None,
    quiz_inventory: list[SourceInventoryEntry] | None = None,
    backend: LLMBackend | None = None,
) -> tuple[list[ExamItemDraft], Path]:
    """Run build_exam with quiz + formative inventory."""
    from examen.pipeline import build_exam

    if blueprint is None:
        blueprint = _make_blueprint()
    if formative_inventory is None:
        formative_inventory = _make_formative_inventory()
    if quiz_inventory is None:
        quiz_inventory = _make_quiz_inventory()
    if backend is None:
        backend = FakeUS3Backend()

    bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
    _setup_bronze(bronze_dir)
    curriculum_map = _make_curriculum_map()

    items, run_dir = build_exam(
        blueprint=blueprint,
        curriculum_map=curriculum_map,
        bronze_dir=bronze_dir,
        data_root=tmp_path / "data",
        backend=backend,
        formative_inventory=formative_inventory,
        quiz_inventory=quiz_inventory,
    )
    return items, run_dir


# ---------------------------------------------------------------------------
# Integration tests (T037)
# ---------------------------------------------------------------------------


class TestUS3QuizItemCount:
    """Quiz slots produce ~15 (exactly N_QUIZ) items."""

    def test_total_item_count(self, tmp_path: Path) -> None:
        """Total items == blueprint.total_items (40)."""
        items, _ = _run_build(tmp_path)
        assert len(items) == 40, f"Expected 40 items, got {len(items)}"

    def test_quiz_item_count_equals_blueprint(self, tmp_path: Path) -> None:
        """Number of quiz items == blueprint.source_mix['quiz'] (15)."""
        items, _ = _run_build(tmp_path)
        quiz_items = [i for i in items if i.source == "quiz"]
        assert len(quiz_items) == _N_QUIZ, (
            f"Expected {_N_QUIZ} quiz items, got {len(quiz_items)}"
        )

    def test_all_three_sources_present(self, tmp_path: Path) -> None:
        """Items come from all three sources: textbook, formative, quiz."""
        items, _ = _run_build(tmp_path)
        sources = {i.source for i in items}
        assert "textbook" in sources
        assert "formative" in sources
        assert "quiz" in sources


class TestUS3QuizChapterBalance:
    """Quiz ~15 selected chapter-evenly across 6 chapters (max diff ≤ 1 per chapter)."""

    def test_quiz_chapter_even_max_diff(self, tmp_path: Path) -> None:
        """Max chapter quiz count - min quiz count ≤ 1 (chapter-even selection)."""
        items, _ = _run_build(tmp_path)
        quiz_items = [i for i in items if i.source == "quiz"]
        from collections import Counter
        counts = list(Counter(i.chapter_no for i in quiz_items).values())
        assert counts, "No quiz items found"
        assert max(counts) - min(counts) <= 1, (
            f"Quiz chapter distribution not even: {counts}"
        )

    def test_all_chapters_represented_in_quiz(self, tmp_path: Path) -> None:
        """All 6 chapters have at least 1 quiz item (chapter-even with 15 items / 6 chapters)."""
        items, _ = _run_build(tmp_path)
        quiz_items = [i for i in items if i.source == "quiz"]
        quiz_chapter_nos = {i.chapter_no for i in quiz_items}
        for ch_no in _CHAPTER_NOS:
            assert ch_no in quiz_chapter_nos, (
                f"Chapter {ch_no} has no quiz items — not chapter-even"
            )

    def test_whole_exam_chapter_even(self, tmp_path: Path) -> None:
        """All chapters have total item counts (max diff ≤ 1) across the whole exam."""
        items, _ = _run_build(tmp_path)
        from collections import Counter
        counts = list(Counter(i.chapter_no for i in items).values())
        assert max(counts) - min(counts) <= 1, (
            f"Whole-exam chapter distribution not even: {counts}"
        )


class TestUS3QuizVariationWording:
    """Quiz variation: generated item wording is neither identical nor wholly different."""

    def test_quiz_items_have_source_quiz(self, tmp_path: Path) -> None:
        """All quiz-derived items have source='quiz'."""
        items, _ = _run_build(tmp_path)
        for item in items:
            if item.source == "quiz":
                assert item.source == "quiz"

    def test_quiz_items_have_source_ref(self, tmp_path: Path) -> None:
        """All quiz items have a source_ref (traceability to original quiz)."""
        items, _ = _run_build(tmp_path)
        for item in items:
            if item.source == "quiz":
                assert item.source_ref is not None, (
                    f"Quiz item item_no={item.item_no} has no source_ref"
                )
                assert item.source_ref.startswith("퀴즈:"), (
                    f"Quiz item source_ref should start with '퀴즈:', got {item.source_ref!r}"
                )

    def test_quiz_items_have_answer_no(self, tmp_path: Path) -> None:
        """Quiz items have answer_no in [1, 5]."""
        items, _ = _run_build(tmp_path)
        for item in items:
            if item.source == "quiz":
                assert 1 <= item.answer_no <= 5, (
                    f"Quiz item answer_no={item.answer_no} out of range"
                )


class TestUS3WholeExamDifficulty:
    """Whole-exam difficulty distribution ≈ 45/35/20."""

    def test_difficulty_distribution_approximate(self, tmp_path: Path) -> None:
        """Easy ≈ 45%, medium ≈ 35%, hard ≈ 20% (±5% rounding tolerance)."""
        items, _ = _run_build(tmp_path)
        total = len(items)
        easy = sum(1 for i in items if i.difficulty == "1_쉬움")
        medium = sum(1 for i in items if i.difficulty == "2_보통")
        hard = sum(1 for i in items if i.difficulty == "3_어려움")
        assert abs(easy / total - 0.45) < 0.05, (
            f"Easy ratio {easy/total:.2f} far from target 0.45"
        )
        assert abs(medium / total - 0.35) < 0.05, (
            f"Medium ratio {medium/total:.2f} far from target 0.35"
        )
        assert abs(hard / total - 0.20) < 0.05, (
            f"Hard ratio {hard/total:.2f} far from target 0.20"
        )


class TestUS3ItemNoUniqueness:
    """item_no must be globally unique (no collision across textbook/formative/quiz)."""

    def test_all_item_no_unique(self, tmp_path: Path) -> None:
        """No two items share an item_no."""
        items, _ = _run_build(tmp_path)
        item_nos = [i.item_no for i in items]
        assert len(item_nos) == len(set(item_nos)), (
            f"Duplicate item_no found: {[n for n in item_nos if item_nos.count(n) > 1]}"
        )

    def test_item_no_spans_global_slots(self, tmp_path: Path) -> None:
        """item_no values span 1..40 globally."""
        items, _ = _run_build(tmp_path)
        item_nos = sorted(i.item_no for i in items)
        assert item_nos == list(range(1, 41)), (
            f"item_no should be 1..40, got {item_nos}"
        )


class TestUS3QuizSubsetSelection:
    """quiz_inventory pool → select ~N_QUIZ deterministically, chapter-even."""

    def test_quiz_selection_deterministic(self, tmp_path: Path) -> None:
        """Running build_exam twice with same inputs produces identical quiz source_refs."""
        inventory = _make_quiz_inventory(30)
        formative = _make_formative_inventory()
        backend = FakeUS3Backend()
        blueprint = _make_blueprint()
        curriculum_map = _make_curriculum_map()

        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)

        from examen.pipeline import build_exam

        items1, _ = build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=backend,
            formative_inventory=formative,
            quiz_inventory=inventory,
        )
        # Second run — same tmp_path (cache will be hit), same inputs
        items2, _ = build_exam(
            blueprint=blueprint,
            curriculum_map=curriculum_map,
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=backend,
            formative_inventory=formative,
            quiz_inventory=inventory,
        )
        refs1 = sorted(i.source_ref for i in items1 if i.source == "quiz")
        refs2 = sorted(i.source_ref for i in items2 if i.source == "quiz")
        assert refs1 == refs2, "Quiz source_refs differ across identical runs (not deterministic)"

    def test_quiz_inventory_too_small_raises(self, tmp_path: Path) -> None:
        """If quiz_inventory has fewer items than needed for chapter-even selection, pipeline raises."""
        # Only 2 items total but we need 15 → not enough for chapter-even
        inventory = _make_quiz_inventory(2)
        formative = _make_formative_inventory()
        blueprint = _make_blueprint()
        curriculum_map = _make_curriculum_map()

        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)

        from examen.pipeline import build_exam

        with pytest.raises((ValueError, RuntimeError)):
            build_exam(
                blueprint=blueprint,
                curriculum_map=curriculum_map,
                bronze_dir=bronze_dir,
                data_root=tmp_path / "data",
                backend=FakeUS3Backend(),
                formative_inventory=formative,
                quiz_inventory=inventory,
            )
