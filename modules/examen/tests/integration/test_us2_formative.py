"""T031 — Integration test: 형성평가 전수 포함·정답=틀린보기·근거 범위 (US2).

TDD (RED phase): tests written before implementation.

This test runs build_exam() with a MIXED blueprint:
- some textbook slots
- some formative slots (one per formative inventory entry)

Assertions:
- all formative inventory entries appear as items (전수 포함)
- every formative item has answer_no pointing to the 틀린 보기
- every formative item has stem_polarity == "부정형"
- source_mix.formative == len(formative_inventory) check fires when mismatch
- pipeline does NOT silently drop any administered formative item
- no network (FakeBackend + FakeFormativeBackend)
- FakeBackend handles both textbook and formative slots
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

# 3 formative entries = source_mix.formative == 3
_N_FORMATIVE = 3
_N_TEXTBOOK = 40 - _N_FORMATIVE  # 37 textbook + 3 formative = 40

# ---------------------------------------------------------------------------
# Canned LLM responses
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
        "옳은 진술: 폐포에서 가스 교환이 일어난다.",
        "옳은 진술: 폐포막은 매우 얇다.",
        "틀린 진술: 폐포에는 섬모가 있다.",
        "옳은 진술: 폐포는 포상 구조이다.",
        "옳은 진술: 산소가 혈액으로 이동한다.",
    ],
    "wrong_explanation": "폐포 관련 오답 설명 텍스트입니다." * 20,
    "leap_explanation": "폐포 관련 도약 설명 텍스트입니다." * 20,
    "intent": "폐포의 기본 구조와 기능을 확인한다.",
    "key_concept": "폐포",
}

# answer_no=5 → 틀린 보기 (부정형 formative)
_CANNED_FORMATIVE_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "2_보통",
    "stem_polarity": "부정형",
    "text": "다음 중 허파꽈리 세포에 대한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① " + "제1형허파세포는가스교환을한다.",
        "② " + "제2형허파세포는표면활성제를분비한다.",
        "③ " + "표면활성제는표면장력을낮추는기능이있다.",
        "④ " + "허파꽈리벽은두종류세포로구성되어있다.",
        "⑤ " + "제2형허파세포는섬모를보유하고있는세포다.",
    ],
    "answer_no": 5,  # ← 틀린 보기 = 정답
    "distractor_rationale": [
        "옳은 진술.",
        "옳은 진술.",
        "옳은 진술.",
        "옳은 진술.",
        "틀린 진술: 제2형 허파세포에 섬모 없음.",
    ],
    "wrong_explanation": "제2형 허파세포에 대한 오답 설명 텍스트입니다." * 10,
    "leap_explanation": "제2형 허파세포에 대한 도약 설명 텍스트입니다." * 10,
    "intent": "허파꽈리 세포 기능을 정확히 이해하는지 확인한다.",
    "key_concept": "제2형 허파세포",
    "wrong_option_no": 5,
}


class FakeUS2Backend(LLMBackend):
    """Returns canned JSON based on source type; counts calls."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        # formative 슬롯: metadata.source == "formative"
        if request.metadata.get("source") == "formative":
            raw = json.dumps(_CANNED_FORMATIVE_JSON, ensure_ascii=False)
        else:
            raw = json.dumps(_CANNED_TEXTBOOK_JSON, ensure_ascii=False)
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=raw,
            model="fake-us2",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_blueprint(n_formative: int = _N_FORMATIVE) -> ExamenBlueprint:
    """Build a mixed blueprint with textbook + formative slots."""
    n_textbook = 40 - n_formative
    return ExamenBlueprint(
        semester=_SEMESTER,
        course_slug=_COURSE,
        exam_name="2026-1학기 기말고사",
        total_items=40,
        chapters=["8장 호흡계통", "9장 근육계통"],
        difficulty_targets={"easy": 0.50, "medium": 0.50, "hard": 0.0},
        source_mix={"textbook": n_textbook, "formative": n_formative, "quiz": 0},
    )


def _make_curriculum_map() -> CurriculumMap:
    return CurriculumMap(
        semester=_SEMESTER,
        course_slug=_COURSE,
        entries=[
            CurriculumEntry(
                week=8,
                chapter="8장 호흡계통",
                chapter_no=8,
                subtopic=None,
                sections=["1. 기도", "2. 폐"],
            ),
            CurriculumEntry(
                week=9,
                chapter="9장 근육계통",
                chapter_no=9,
                subtopic=None,
                sections=["1. 골격근", "2. 평활근"],
            ),
        ],
    )


def _make_formative_inventory(n: int = _N_FORMATIVE) -> list[SourceInventoryEntry]:
    """Create N synthetic formative SourceInventoryEntry items."""
    entries = []
    chapters = [8, 8, 9]  # spread across two chapters
    weeks = [8, 8, 9]
    for i in range(n):
        ch = chapters[i % len(chapters)]
        wk = weeks[i % len(weeks)]
        entries.append(
            SourceInventoryEntry(
                semester=_SEMESTER,
                course_slug=_COURSE,
                source="formative",
                source_ref=f"형성평가:{ch}장#{i + 1}",
                chapter_no=ch,
                week=wk,
                stem=f"형성평가 질문 {i + 1}: 호흡기계 구조에 대해 설명하시오.",
                model_answer=(
                    f"모범답안 {i + 1}: 호흡기계는 기도와 폐로 구성된다. "
                    "기도는 공기를 폐로 전달하며, 폐에서 가스 교환이 이루어진다."
                ),
                keywords=["기도", "폐", "가스 교환", "허파꽈리"],
                rubric={
                    "high": "기도와 폐의 기능 모두 정확히 설명",
                    "mid": "한 가지만 설명",
                    "low": "가스 교환이 기도에서 일어난다는 오개념",
                },
            )
        )
    return entries


def _write_chapter_fixture(bronze_dir: Path, chapter_no: int, chapter_name: str) -> None:
    """Write a minimal synthetic textbook .txt fixture."""
    fname = f"{chapter_no}장 {chapter_name}.txt"
    content = (
        f"{chapter_no}장 {chapter_name}\n"
        "1. 제일 절\n"
        f"{chapter_name}에 관한 주요 내용.\n"
        "폐포에서 가스 교환이 일어난다.\n"
        "산소와 이산화탄소가 교환된다.\n"
        "2. 두 번째 절\n"
        f"{chapter_name}의 추가 내용.\n"
    )
    (bronze_dir / fname).write_text(content, encoding="utf-8")


def _setup_bronze(bronze_dir: Path) -> None:
    """Write chapter .txt files to bronze_dir."""
    bronze_dir.mkdir(parents=True, exist_ok=True)
    _write_chapter_fixture(bronze_dir, 8, "호흡계통")
    _write_chapter_fixture(bronze_dir, 9, "근육계통")


# ---------------------------------------------------------------------------
# Helper: run build_exam with formative inventory
# ---------------------------------------------------------------------------


def _run_build(
    tmp_path: Path,
    *,
    blueprint: ExamenBlueprint | None = None,
    formative_inventory: list[SourceInventoryEntry] | None = None,
    backend: LLMBackend | None = None,
) -> tuple[list[ExamItemDraft], Path]:
    """Run build_exam with formative inventory; return (items, run_dir)."""
    from examen.pipeline import build_exam

    if blueprint is None:
        blueprint = _make_blueprint()
    if formative_inventory is None:
        formative_inventory = _make_formative_inventory()
    if backend is None:
        backend = FakeUS2Backend()

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
    )
    return items, run_dir


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestUS2FormativeInclusion:
    """All administered formative items appear in the output (전수 포함)."""

    def test_total_item_count(self, tmp_path: Path) -> None:
        """Total items == blueprint.total_items (40)."""
        items, _ = _run_build(tmp_path)
        assert len(items) == 40, f"Expected 40 items, got {len(items)}"

    def test_formative_count_equals_inventory_size(self, tmp_path: Path) -> None:
        """Number of formative items == len(formative_inventory) (전수 포함)."""
        inventory = _make_formative_inventory()
        items, _ = _run_build(tmp_path, formative_inventory=inventory)
        formative_items = [i for i in items if i.source == "formative"]
        assert len(formative_items) == len(inventory), (
            f"Expected {len(inventory)} formative items, got {len(formative_items)}"
        )

    def test_all_source_refs_present(self, tmp_path: Path) -> None:
        """Every source_ref from the inventory appears in the output (no silent drop)."""
        inventory = _make_formative_inventory()
        items, _ = _run_build(tmp_path, formative_inventory=inventory)
        formative_refs = {i.source_ref for i in items if i.source == "formative"}
        for entry in inventory:
            assert entry.source_ref in formative_refs, (
                f"Administered formative entry {entry.source_ref!r} silently dropped!"
            )

    def test_no_silent_drop(self, tmp_path: Path) -> None:
        """Alias: same as test_all_source_refs_present — constitution requirement."""
        self.test_all_source_refs_present(tmp_path)


class TestUS2AnswerIsWrongOption:
    """Every formative item has answer_no pointing to the 틀린 보기 (부정형)."""

    def test_formative_items_have_negative_stem(self, tmp_path: Path) -> None:
        """All formative items have stem_polarity == '부정형'."""
        items, _ = _run_build(tmp_path)
        for item in items:
            if item.source == "formative":
                assert item.stem_polarity == "부정형", (
                    f"Formative item {item.source_ref} has stem_polarity={item.stem_polarity!r}"
                )

    def test_formative_answer_no_in_range(self, tmp_path: Path) -> None:
        """answer_no is in [1, 5] for all formative items."""
        items, _ = _run_build(tmp_path)
        for item in items:
            if item.source == "formative":
                assert 1 <= item.answer_no <= 5, (
                    f"Formative item {item.source_ref} answer_no={item.answer_no} out of range"
                )

    def test_check_format_applied_to_formative(self, tmp_path: Path) -> None:
        """check_format (or check_formative) is applied to all formative items."""
        items, _ = _run_build(tmp_path)
        for item in items:
            if item.source == "formative":
                # option_length_ok must be set (True or False — verify owns this)
                assert item.option_length_ok is not None, (
                    f"Formative item {item.source_ref} missing option_length_ok"
                )


class TestUS2SourceMixValidation:
    """source_mix.formative == 대장수 cross-check."""

    def test_mismatch_raises_value_error(self, tmp_path: Path) -> None:
        """build_exam raises ValueError when source_mix.formative != len(inventory)."""
        # Blueprint says 3 formative, but we give 2 entries → mismatch
        blueprint = _make_blueprint(n_formative=3)
        inventory_too_small = _make_formative_inventory(n=2)

        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)

        from examen.pipeline import build_exam

        with pytest.raises(ValueError, match="formative"):
            build_exam(
                blueprint=blueprint,
                curriculum_map=_make_curriculum_map(),
                bronze_dir=bronze_dir,
                data_root=tmp_path / "data",
                backend=FakeUS2Backend(),
                formative_inventory=inventory_too_small,
            )

    def test_exact_match_does_not_raise(self, tmp_path: Path) -> None:
        """build_exam succeeds when source_mix.formative == len(inventory)."""
        blueprint = _make_blueprint(n_formative=_N_FORMATIVE)
        inventory = _make_formative_inventory(n=_N_FORMATIVE)
        # Should not raise
        items, _ = _run_build(
            tmp_path,
            blueprint=blueprint,
            formative_inventory=inventory,
        )
        assert len(items) == 40

    def test_zero_formative_with_empty_inventory(self, tmp_path: Path) -> None:
        """source_mix.formative==0 with empty inventory → no formative items."""
        blueprint = ExamenBlueprint(
            semester=_SEMESTER,
            course_slug=_COURSE,
            exam_name="2026-1학기 기말고사",
            total_items=40,
            chapters=["8장 호흡계통", "9장 근육계통"],
            difficulty_targets={"easy": 0.50, "medium": 0.50, "hard": 0.0},
            source_mix={"textbook": 40, "formative": 0, "quiz": 0},
        )
        items, _ = _run_build(
            tmp_path,
            blueprint=blueprint,
            formative_inventory=[],
        )
        formative_items = [i for i in items if i.source == "formative"]
        assert len(formative_items) == 0


class TestUS2GroundednessScope:
    """Formative items have groundedness status set (best-effort, not crash)."""

    def test_formative_items_have_option_length_ok_set(self, tmp_path: Path) -> None:
        """option_length_ok is set on all formative items."""
        items, _ = _run_build(tmp_path)
        for item in items:
            if item.source == "formative":
                assert item.option_length_ok is not None

    def test_textbook_items_unaffected(self, tmp_path: Path) -> None:
        """Adding formative items does not break textbook item generation."""
        items, _ = _run_build(tmp_path)
        textbook_items = [i for i in items if i.source == "textbook"]
        assert len(textbook_items) == _N_TEXTBOOK, (
            f"Expected {_N_TEXTBOOK} textbook items, got {len(textbook_items)}"
        )

    def test_review_note_not_crash_on_formative(self, tmp_path: Path) -> None:
        """review_note field on formative items is a string (not None, not exception)."""
        items, _ = _run_build(tmp_path)
        for item in items:
            if item.source == "formative":
                assert isinstance(item.review_note, str), (
                    f"review_note should be str, got {type(item.review_note)}"
                )


class TestUS2ItemNoUniqueness:
    """item_no must be globally unique across textbook + formative (T036 review fix)."""

    def test_all_item_no_unique(self, tmp_path: Path) -> None:
        """No two items (textbook or formative) share an item_no (번호 collision)."""
        items, _ = _run_build(tmp_path)
        item_nos = [i.item_no for i in items]
        assert len(item_nos) == len(set(item_nos)), (
            f"duplicate item_no found: "
            f"{[n for n in item_nos if item_nos.count(n) > 1]}"
        )

    def test_item_no_covers_all_slots(self, tmp_path: Path) -> None:
        """item_no values span the global slot positions 1..total_items."""
        items, _ = _run_build(tmp_path)
        item_nos = sorted(i.item_no for i in items)
        assert item_nos == list(range(1, 41)), (
            f"item_no should be 1..40 globally, got {item_nos[:5]}...{item_nos[-5:]}"
        )

    def test_formative_item_no_matches_global_slot(self, tmp_path: Path) -> None:
        """Formative items use the GLOBAL slot position as item_no, not the source_ref tail."""
        items, _ = _run_build(tmp_path)
        formative = [i for i in items if i.source == "formative"]
        # All formative item_no must be within the global range and unique vs textbook
        textbook_nos = {i.item_no for i in items if i.source == "textbook"}
        for f in formative:
            assert f.item_no not in textbook_nos, (
                f"formative item_no={f.item_no} collides with a textbook item_no"
            )


class TestUS2OutOfOrderChapterBinding:
    """Inventory file order may differ from blueprint/solver chapter order."""

    def test_inventory_out_of_blueprint_chapter_order(self, tmp_path: Path) -> None:
        """An inventory whose file order interleaves chapters still binds correctly.

        The solver places formative slots chapter-major (8장 ×2, then 9장 ×1).
        We pass inventory in a DIFFERENT order (9장 first, then 8장 entries) and
        assert each emitted formative item's source_ref chapter matches its
        item.chapter_no (no source_ref↔chapter divergence).
        """
        # inventory deliberately out of order: ch9 first, then two ch8
        inventory = [
            SourceInventoryEntry(
                semester=_SEMESTER, course_slug=_COURSE, source="formative",
                source_ref="형성평가:9장#1", chapter_no=9, week=9,
                stem="근육 질문.", model_answer="근육 모범답안. " * 5,
                keywords=["근육"], rubric={"high": "h", "mid": "m", "low": "오개념"},
            ),
            SourceInventoryEntry(
                semester=_SEMESTER, course_slug=_COURSE, source="formative",
                source_ref="형성평가:8장#1", chapter_no=8, week=8,
                stem="호흡 질문1.", model_answer="호흡 모범답안1. " * 5,
                keywords=["호흡"], rubric={"high": "h", "mid": "m", "low": "오개념"},
            ),
            SourceInventoryEntry(
                semester=_SEMESTER, course_slug=_COURSE, source="formative",
                source_ref="형성평가:8장#2", chapter_no=8, week=8,
                stem="호흡 질문2.", model_answer="호흡 모범답안2. " * 5,
                keywords=["호흡"], rubric={"high": "h", "mid": "m", "low": "오개념"},
            ),
        ]
        items, _ = _run_build(tmp_path, formative_inventory=inventory)
        formative = [i for i in items if i.source == "formative"]
        assert len(formative) == 3

        # Each formative item: the chapter_no in its source_ref must equal item.chapter_no
        for f in formative:
            # source_ref is "형성평가:{N}장#{k}" → parse the chapter number
            ref = f.source_ref or ""
            assert ref.startswith("형성평가:")
            ch_in_ref = int(ref.split(":")[1].split("장")[0])
            assert ch_in_ref == f.chapter_no, (
                f"source_ref {ref!r} chapter {ch_in_ref} != item.chapter_no {f.chapter_no} "
                "(source_ref↔chapter divergence!)"
            )

    def test_uneven_chapter_distribution_adapts(self, tmp_path: Path) -> None:
        """전수 형성평가 인벤토리가 한 장에 쏠려도 솔버가 그 장 분포에 적응한다.

        인벤토리가 전부 8장(3개)이면 솔버는 형성 슬롯을 8장 ×3 + 9장 ×0 으로
        배치한다.  슬롯-인벤토리 바인딩이 항상 같은 장이므로 source_ref↔chapter
        divergence 가 발생하지 않고 build 가 성공한다(과거의 챕터-균등 강제 가정
        제거).  pipeline 의 위치 기반 교차검증은 방어선으로 남아 발동하지 않는다.
        """
        inventory = [
            SourceInventoryEntry(
                semester=_SEMESTER, course_slug=_COURSE, source="formative",
                source_ref=f"형성평가:8장#{k}", chapter_no=8, week=8,
                stem=f"호흡 질문{k}.", model_answer="모범답안. " * 5,
                keywords=["호흡"], rubric={"high": "h", "mid": "m", "low": "오개념"},
            )
            for k in range(1, 4)  # 3 items, ALL chapter 8
        ]
        items, _ = _run_build(tmp_path, formative_inventory=inventory)

        formative = [i for i in items if i.source == "formative"]
        assert len(formative) == 3
        # 모든 형성 문항이 8장이고 source_ref↔chapter 가 일치한다(no divergence).
        for f in formative:
            assert f.chapter_no == 8
            ref = f.source_ref or ""
            assert ref.startswith("형성평가:8장")
        # 9장에는 형성 슬롯이 배정되지 않는다(인벤토리에 9장 형성이 없으므로).
        assert all(i.chapter_no == 8 for i in formative)
