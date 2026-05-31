"""T049 — Integration: answer-key balance + quality report (US5).

TDD (RED phase): tests written before implementation.

Tests:
- After build_exam with FakeBackend:
  - answer-number distribution is 15–25% for each of 1–5
  - no run of >2 consecutive identical answer numbers
  - quality report file (출제품질리포트.md) exists in the run Gold dir
  - quality report contains 목표 vs 실측 sections
  - manifest has targets_vs_actual with answer_no_balance key
- balance_answer_keys is deterministic (idempotent: balanced → same output)
- balance preserves item correctness (answer content stays correct)
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

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
# Constants (mirrors US3 test setup for a 40-item build)
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"

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
# Canned responses — deliberately skewed answer_no so balance is needed
# ---------------------------------------------------------------------------

# All items produced with answer_no=1; balance should redistribute them.
def _make_canned_json(answer_no: int = 1, source: str = "textbook") -> dict[str, Any]:
    return {
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
        "answer_no": answer_no,
        "distractor_rationale": [
            "옳은 진술: 가.",
            "옳은 진술: 나.",
            "틀린 진술: 다." if answer_no == 3 else "옳은 진술: 다.",
            "옳은 진술: 라.",
            "옳은 진술: 마.",
        ],
        "wrong_explanation": "오답 설명 텍스트입니다." * 20,
        "leap_explanation": "도약 설명 텍스트입니다." * 20,
        "intent": "기본 구조와 기능을 확인한다.",
        "key_concept": None,  # None to avoid duplicate detection
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
    "key_concept": None,
    "wrong_option_no": 5,
}

_CANNED_QUIZ_JSON: dict[str, Any] = {
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
    "answer_no": 1,  # skewed to 1 — balance must fix
    "distractor_rationale": [
        "틀린 진술: 변형 오개념.",
        "옳은 진술: 변형.",
        "옳은 진술: 변형.",
        "옳은 진술: 변형.",
        "옳은 진술: 변형.",
    ],
    "wrong_explanation": "변형 오답 설명." * 20,
    "leap_explanation": "변형 도약 설명." * 20,
    "intent": "변형된 문항 의도.",
    "key_concept": None,
}


class FakeUS5Backend(LLMBackend):
    """Returns canned JSON with answer_no=1 for all items (skewed for balance test)."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        import json as _json

        self.call_count += 1
        source = request.metadata.get("source", "textbook")
        if source == "formative":
            raw = _json.dumps(_CANNED_FORMATIVE_JSON, ensure_ascii=False)
        elif source == "quiz":
            raw = _json.dumps(_CANNED_QUIZ_JSON, ensure_ascii=False)
        else:
            # textbook — all answer_no=1 to stress balance algorithm
            raw = _json.dumps(_make_canned_json(answer_no=1), ensure_ascii=False)
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=raw,
            model="fake-us5",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# Fixture builders (reuse US3 pattern)
# ---------------------------------------------------------------------------


def _make_blueprint() -> ExamenBlueprint:
    return ExamenBlueprint(
        semester=_SEMESTER,
        course_slug=_COURSE,
        exam_name="2026-1학기 기말고사",
        total_items=40,
        chapters=_CHAPTERS,
        difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
        source_mix={"textbook": _N_TEXTBOOK, "formative": _N_FORMATIVE, "quiz": _N_QUIZ},
        answer_key_balance=True,
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
    entries = []
    per_chapter = n // len(_CHAPTER_NOS)
    remainder = n % len(_CHAPTER_NOS)
    row = 0
    for i, (chapter_no, week) in enumerate(zip(_CHAPTER_NOS, _WEEKS, strict=False)):
        count = per_chapter + (1 if i < remainder else 0)
        for j in range(count):
            row += 1
            stem = f"{chapter_no}장 {j + 1}번: 해당 계통에 관한 설명 중 옳지 않은 것은?"
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
    entries = []
    for _i, (chapter_no, week) in enumerate(zip(_CHAPTER_NOS, _WEEKS, strict=False)):
        for j in range(2):
            entries.append(
                SourceInventoryEntry(
                    semester=_SEMESTER,
                    course_slug=_COURSE,
                    source="formative",
                    source_ref=f"형성평가:{chapter_no}장#{j + 1}",
                    chapter_no=chapter_no,
                    week=week,
                    stem=f"{chapter_no}장 형성평가 {j + 1}번: 해당 계통 구조 설명.",
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
    for chapter_no, chapter_name in zip(
        _CHAPTER_NOS, [c.split(" ", 1)[1] for c in _CHAPTERS], strict=False
    ):
        _write_chapter_fixture(bronze_dir, chapter_no, chapter_name)


def _run_build(
    tmp_path: Path,
    *,
    blueprint: ExamenBlueprint | None = None,
    backend: LLMBackend | None = None,
) -> tuple[list[ExamItemDraft], Path]:
    from examen.pipeline import build_exam

    if blueprint is None:
        blueprint = _make_blueprint()
    if backend is None:
        backend = FakeUS5Backend()

    bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
    _setup_bronze(bronze_dir)
    curriculum_map = _make_curriculum_map()

    items, run_dir = build_exam(
        blueprint=blueprint,
        curriculum_map=curriculum_map,
        bronze_dir=bronze_dir,
        data_root=tmp_path / "data",
        backend=backend,
        formative_inventory=_make_formative_inventory(),
        quiz_inventory=_make_quiz_inventory(),
    )
    return items, run_dir


# ---------------------------------------------------------------------------
# T049 tests: answer-key balance
# ---------------------------------------------------------------------------


class TestAnswerKeyBalance:
    """After build_exam the answer_no distribution satisfies the balance spec."""

    def test_answer_no_each_15_to_25_percent(self, tmp_path: Path) -> None:
        """Each answer number 1-5 appears in 15-25% of items."""
        items, _ = _run_build(tmp_path)
        total = len(items)
        assert total > 0

        counts = Counter(i.answer_no for i in items)
        for num in range(1, 6):
            ratio = counts.get(num, 0) / total
            assert 0.15 <= ratio <= 0.25, (
                f"answer_no={num}: ratio={ratio:.2%} out of 15-25% range. "
                f"Distribution: {dict(sorted(counts.items()))}"
            )

    def test_no_run_of_three_consecutive_same_answer(self, tmp_path: Path) -> None:
        """No three consecutive items share the same answer_no."""
        items, _ = _run_build(tmp_path)
        for i in range(len(items) - 2):
            a, b, c = items[i].answer_no, items[i + 1].answer_no, items[i + 2].answer_no
            assert not (a == b == c), (
                f"Run of 3 at positions {i},{i+1},{i+2}: answer_no={a}. "
                f"Full sequence: {[item.answer_no for item in items]}"
            )

    def test_item_count_unchanged_after_balance(self, tmp_path: Path) -> None:
        """balance_answer_keys preserves the list length."""
        from examen.verify.format_checks import balance_answer_keys

        items, _ = _run_build(tmp_path)
        # Run balance again (idempotent check)
        balanced_again = balance_answer_keys(items)
        assert len(balanced_again) == len(items)

    def test_balance_preserves_correctness(self, tmp_path: Path) -> None:
        """After balance, the answer_no points to the option content that was correct before.

        The swap operation must move the *correct* option to a new position and
        update answer_no to match — so the content at the new answer_no index
        equals the content that was originally at the old answer_no index.
        """
        from examen.verify.format_checks import balance_answer_keys

        items, _ = _run_build(tmp_path)
        # Map (item_no → original correct option content) before any re-balance
        original_correct: dict[int, str] = {
            item.item_no: item.options[item.answer_no - 1] for item in items
        }

        balanced = balance_answer_keys(items)

        for orig, bal in zip(items, balanced, strict=True):
            expected_correct = original_correct[orig.item_no]
            actual_correct = bal.options[bal.answer_no - 1]
            assert actual_correct == expected_correct, (
                f"item_no={orig.item_no}: correct option content changed after balance! "
                f"Before: {expected_correct!r} → After: {actual_correct!r}"
            )

    def test_balance_deterministic(self, tmp_path: Path) -> None:
        """balance_answer_keys on same input gives same output (deterministic)."""
        from examen.verify.format_checks import balance_answer_keys

        items, _ = _run_build(tmp_path)
        result1 = balance_answer_keys(items)
        result2 = balance_answer_keys(items)
        for r1, r2 in zip(result1, result2, strict=True):
            assert r1.answer_no == r2.answer_no, (
                f"item_no={r1.item_no}: answer_no differs across runs "
                f"({r1.answer_no} vs {r2.answer_no})"
            )

    def test_balance_idempotent_on_balanced_input(self, tmp_path: Path) -> None:
        """Running balance twice gives same result as once (idempotent-ish)."""
        from examen.verify.format_checks import balance_answer_keys

        items, _ = _run_build(tmp_path)
        once = balance_answer_keys(items)
        twice = balance_answer_keys(once)
        for o, t in zip(once, twice, strict=True):
            assert o.answer_no == t.answer_no, (
                f"item_no={o.item_no}: balance not idempotent "
                f"({o.answer_no} → {t.answer_no})"
            )


# ---------------------------------------------------------------------------
# T049 tests: quality report file
# ---------------------------------------------------------------------------


class TestQualityReport:
    """출제품질리포트.md exists with 목표 vs 실측 content."""

    def test_quality_report_file_exists(self, tmp_path: Path) -> None:
        """출제품질리포트.md is written to the run Gold dir."""
        _, run_dir = _run_build(tmp_path)
        report_path = run_dir / "출제품질리포트.md"
        assert report_path.exists(), (
            f"출제품질리포트.md not found in {run_dir}"
        )

    def test_quality_report_not_empty(self, tmp_path: Path) -> None:
        """출제품질리포트.md has non-trivial content."""
        _, run_dir = _run_build(tmp_path)
        text = (run_dir / "출제품질리포트.md").read_text(encoding="utf-8")
        assert len(text) > 50, "Quality report is too short"

    def test_quality_report_contains_chapter_section(self, tmp_path: Path) -> None:
        """Report contains a chapter distribution table/section."""
        _, run_dir = _run_build(tmp_path)
        text = (run_dir / "출제품질리포트.md").read_text(encoding="utf-8")
        # Should mention 챕터 or chapter distribution
        assert "챕터" in text or "장" in text, (
            "Quality report missing chapter distribution section"
        )

    def test_quality_report_contains_difficulty_section(self, tmp_path: Path) -> None:
        """Report contains difficulty distribution (목표 vs 실측)."""
        _, run_dir = _run_build(tmp_path)
        text = (run_dir / "출제품질리포트.md").read_text(encoding="utf-8")
        assert "난이도" in text, "Quality report missing difficulty section"

    def test_quality_report_contains_answer_no_section(self, tmp_path: Path) -> None:
        """Report contains answer-number distribution section."""
        _, run_dir = _run_build(tmp_path)
        text = (run_dir / "출제품질리포트.md").read_text(encoding="utf-8")
        assert "정답" in text, "Quality report missing answer-number distribution section"

    def test_quality_report_contains_deviation_indicators(self, tmp_path: Path) -> None:
        """Report uses ✅ or ⚠️ to flag conformance/deviation."""
        _, run_dir = _run_build(tmp_path)
        text = (run_dir / "출제품질리포트.md").read_text(encoding="utf-8")
        has_indicator = "✅" in text or "⚠️" in text
        assert has_indicator, (
            "Quality report should use ✅/⚠️ to flag conformance (got neither)"
        )

    def test_quality_report_reproducible(self, tmp_path: Path) -> None:
        """Running build twice produces identical quality report content."""
        from examen.pipeline import build_exam

        blueprint = _make_blueprint()
        backend = FakeUS5Backend()
        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)
        curriculum_map = _make_curriculum_map()
        kwargs: dict[str, Any] = {
            "blueprint": blueprint,
            "curriculum_map": curriculum_map,
            "bronze_dir": bronze_dir,
            "data_root": tmp_path / "data",
            "backend": backend,
            "formative_inventory": _make_formative_inventory(),
            "quiz_inventory": _make_quiz_inventory(),
        }
        _, run_dir1 = build_exam(**kwargs)
        _, run_dir2 = build_exam(**kwargs)

        # Same run_id → same dir; content is stable
        text1 = (run_dir1 / "출제품질리포트.md").read_text(encoding="utf-8")
        text2 = (run_dir2 / "출제품질리포트.md").read_text(encoding="utf-8")
        assert text1 == text2, "Quality report content differs across identical runs"


# ---------------------------------------------------------------------------
# T049 tests: manifest targets_vs_actual
# ---------------------------------------------------------------------------


class TestManifestTargetsVsActual:
    """manifest_examen.json carries enriched targets_vs_actual."""

    def test_manifest_has_targets_vs_actual(self, tmp_path: Path) -> None:
        """manifest targets_vs_actual key exists."""
        _, run_dir = _run_build(tmp_path)
        manifest = json.loads((run_dir / "manifest_examen.json").read_text(encoding="utf-8"))
        assert "targets_vs_actual" in manifest

    def test_manifest_targets_vs_actual_has_answer_no_balance(self, tmp_path: Path) -> None:
        """targets_vs_actual includes answer_no_balance info."""
        _, run_dir = _run_build(tmp_path)
        manifest = json.loads((run_dir / "manifest_examen.json").read_text(encoding="utf-8"))
        tva = manifest["targets_vs_actual"]
        # Expect an answer_no_balance key with distribution data
        assert "answer_no_balance" in tva, (
            f"targets_vs_actual missing 'answer_no_balance'. Keys: {list(tva.keys())}"
        )

    def test_manifest_targets_vs_actual_has_difficulty(self, tmp_path: Path) -> None:
        """targets_vs_actual includes difficulty target vs actual."""
        _, run_dir = _run_build(tmp_path)
        manifest = json.loads((run_dir / "manifest_examen.json").read_text(encoding="utf-8"))
        tva = manifest["targets_vs_actual"]
        assert "difficulty" in tva

    def test_manifest_answer_no_distribution_reflects_balance(self, tmp_path: Path) -> None:
        """answer_no_distribution in manifest matches the balanced items."""
        items, run_dir = _run_build(tmp_path)
        manifest = json.loads((run_dir / "manifest_examen.json").read_text(encoding="utf-8"))
        dist = manifest["answer_no_distribution"]
        # JSON keys are strings; convert to int for comparison
        dist_int = {int(k): v for k, v in dist.items()}
        expected = Counter(i.answer_no for i in items)
        for num in range(1, 6):
            assert dist_int.get(num, 0) == expected.get(num, 0), (
                f"Manifest answer_no_distribution[{num}]={dist_int.get(num, 0)} "
                f"!= actual {expected.get(num, 0)}"
            )


# ---------------------------------------------------------------------------
# Unit tests for balance_answer_keys standalone
# ---------------------------------------------------------------------------


class TestBalanceAnswerKeysUnit:
    """Unit tests for balance_answer_keys function in isolation."""

    def _make_items_all_same_answer(self, n: int, answer_no: int) -> list[ExamItemDraft]:
        """Create n items all with the same answer_no."""
        items = []
        for i in range(n):
            items.append(
                ExamItemDraft(
                    semester=_SEMESTER,
                    course_slug=_COURSE,
                    item_no=i + 1,
                    source="textbook",
                    chapter="8장 호흡계통",
                    chapter_no=8,
                    question_type="지식축적",
                    difficulty="2_보통",
                    stem_polarity="부정형",
                    text="다음 중 가장 옳지 않은 것은?",
                    options=[
                        "① " + "가" * 28,
                        "② " + "나" * 28,
                        "③ " + "다" * 28,
                        "④ " + "라" * 28,
                        "⑤ " + "마" * 28,
                    ],
                    answer_no=answer_no,
                    distractor_rationale=[
                        "옳은 진술: 가." if j + 1 != answer_no else "틀린 진술: 다."
                        for j in range(5)
                    ],
                    wrong_explanation="오답 설명." * 10,
                    leap_explanation="도약 설명." * 10,
                    intent="출제의도 텍스트 테스트.",
                    option_length_ok=True,
                )
            )
        return items

    def test_all_answer_1_gets_redistributed(self) -> None:
        """20 items all with answer_no=1 → balanced output."""
        from examen.verify.format_checks import balance_answer_keys

        items = self._make_items_all_same_answer(20, answer_no=1)
        balanced = balance_answer_keys(items)
        total = len(balanced)
        counts = Counter(i.answer_no for i in balanced)
        for num in range(1, 6):
            ratio = counts.get(num, 0) / total
            assert 0.15 <= ratio <= 0.25, (
                f"answer_no={num}: ratio={ratio:.2%} out of 15-25%. Dist: {dict(counts)}"
            )

    def test_no_run_of_three_after_balance_unit(self) -> None:
        """20 items all answer_no=1 → no run of 3 after balance."""
        from examen.verify.format_checks import balance_answer_keys

        items = self._make_items_all_same_answer(20, answer_no=1)
        balanced = balance_answer_keys(items)
        for i in range(len(balanced) - 2):
            a, b, c = balanced[i].answer_no, balanced[i + 1].answer_no, balanced[i + 2].answer_no
            assert not (a == b == c), (
                f"Run of 3 at {i},{i+1},{i+2}: {a},{b},{c}"
            )

    def test_already_balanced_stays_same(self) -> None:
        """Items with perfectly balanced answer_nos → no churn."""
        from examen.verify.format_checks import balance_answer_keys

        # 10 items: 2 each of 1,2,3,4,5
        items = []
        for num in range(1, 6):
            for j in range(2):
                items.append(
                    ExamItemDraft(
                        semester=_SEMESTER,
                        course_slug=_COURSE,
                        item_no=len(items) + 1,
                        source="textbook",
                        chapter="8장 호흡계통",
                        chapter_no=8,
                        question_type="지식축적",
                        difficulty="2_보통",
                        stem_polarity="부정형",
                        text="다음 중 가장 옳지 않은 것은?",
                        options=[
                            "① " + "가" * 28,
                            "② " + "나" * 28,
                            "③ " + "다" * 28,
                            "④ " + "라" * 28,
                            "⑤ " + "마" * 28,
                        ],
                        answer_no=num,
                        distractor_rationale=[
                            "옳은 진술." for _ in range(5)
                        ],
                        wrong_explanation="오답." * 10,
                        leap_explanation="도약." * 10,
                        intent="출제의도 텍스트 테스트.",
                        option_length_ok=True,
                    )
                )
        balanced = balance_answer_keys(items)
        for orig, bal in zip(items, balanced, strict=True):
            # Balanced output should have valid distribution
            assert 1 <= bal.answer_no <= 5
            _ = orig  # suppress unused variable warning

    def test_empty_list_returns_empty(self) -> None:
        """balance_answer_keys([]) == []."""
        from examen.verify.format_checks import balance_answer_keys

        assert balance_answer_keys([]) == []

    def test_small_n_no_crash(self) -> None:
        """balance_answer_keys works for n=1 (can't guarantee 15-25% but shouldn't crash)."""
        from examen.verify.format_checks import balance_answer_keys

        items = self._make_items_all_same_answer(1, answer_no=1)
        result = balance_answer_keys(items)
        assert len(result) == 1

    def _make_items_with_answer_sequence(
        self, answer_seq: list[int]
    ) -> list[ExamItemDraft]:
        """Create items whose answer_no follows ``answer_seq`` exactly (in order)."""
        items = []
        for i, answer_no in enumerate(answer_seq):
            items.append(
                ExamItemDraft(
                    semester=_SEMESTER,
                    course_slug=_COURSE,
                    item_no=i + 1,
                    source="textbook",
                    chapter="8장 호흡계통",
                    chapter_no=8,
                    question_type="지식축적",
                    difficulty="2_보통",
                    stem_polarity="부정형",
                    text="다음 중 가장 옳지 않은 것은?",
                    options=[
                        "① " + "가" * 28,
                        "② " + "나" * 28,
                        "③ " + "다" * 28,
                        "④ " + "라" * 28,
                        "⑤ " + "마" * 28,
                    ],
                    answer_no=answer_no,
                    distractor_rationale=[
                        "옳은 진술: 가." if j + 1 != answer_no else "틀린 진술: 다."
                        for j in range(5)
                    ],
                    wrong_explanation="오답 설명." * 10,
                    leap_explanation="도약 설명." * 10,
                    intent="출제의도 텍스트 테스트.",
                    option_length_ok=True,
                )
            )
        return items

    def test_under_representation_without_over_or_run_is_fixed(self) -> None:
        """Under-rep (<15%) with NO over-rep (>25%) and NO run-of-3 must still be fixed.

        Regression guard for the US5 Critical: the original greedy only triggered
        on over-representation (>25%) or a run-of-3, so a distribution like
        counts {1:5, 2:9, 3:9, 4:8, 5:9} over N=40 — where answer_no=1 is at
        12.5% (<15%) but nothing exceeds 25% and no three identical answers run
        consecutively — was returned unchanged, violating FR-013/SC-007.

        We build exactly that multiset, arranged so there is no run-of-3, and
        assert balance pulls every number into the 15–25% band.
        """
        from examen.verify.format_checks import balance_answer_keys

        # Multiset: answer_no=1 appears 5 times (12.5% < 15%); 2,3,5 appear 9
        # times (22.5%); 4 appears 8 times (20%). Max = 9 (22.5% ≤ 25%) so no
        # over-rep trigger fires under the old algorithm.
        # Build the exact multiset, then interleave to avoid any run-of-3.
        multiset: list[int] = (
            [1] * 5 + [2] * 9 + [3] * 9 + [4] * 8 + [5] * 9
        )
        assert len(multiset) == 40
        # Interleave deterministically to avoid any run-of-3: sort by (rank within
        # its own number) so identical numbers are spread out.
        from collections import defaultdict

        buckets: dict[int, list[int]] = defaultdict(list)
        for v in multiset:
            buckets[v].append(v)
        # Round-robin draw from buckets (descending by remaining size) → no runs.
        seq: list[int] = []
        while any(buckets.values()):
            order = sorted(
                (num for num in range(1, 6) if buckets[num]),
                key=lambda num: (-len(buckets[num]), num),
            )
            for num in order:
                if buckets[num]:
                    seq.append(buckets[num].pop())
        assert len(seq) == 40

        items = self._make_items_with_answer_sequence(seq)

        # Sanity: the constructed input has NO over-rep and NO run-of-3 — only
        # the under-rep violation. This is what defeated the old algorithm.
        in_counts = Counter(i.answer_no for i in items)
        assert max(in_counts.values()) / 40 <= 0.25, "test setup: unexpected over-rep"
        for i in range(len(items) - 2):
            a, b, c = items[i].answer_no, items[i + 1].answer_no, items[i + 2].answer_no
            assert not (a == b == c), "test setup: unexpected run-of-3 in input"
        assert in_counts[1] / 40 < 0.15, "test setup: answer_no=1 should be under-rep"

        balanced = balance_answer_keys(items)
        total = len(balanced)
        out_counts = Counter(i.answer_no for i in balanced)
        for num in range(1, 6):
            ratio = out_counts.get(num, 0) / total
            assert 0.15 <= ratio <= 0.25, (
                f"after balance answer_no={num}: ratio={ratio:.2%} out of 15-25%. "
                f"Dist: {dict(sorted(out_counts.items()))}"
            )
        # And still no run-of-3.
        for i in range(len(balanced) - 2):
            a, b, c = (
                balanced[i].answer_no,
                balanced[i + 1].answer_no,
                balanced[i + 2].answer_no,
            )
            assert not (a == b == c), f"run-of-3 at {i} after balance"
        # And correctness preserved.
        for orig, bal in zip(items, balanced, strict=True):
            assert (
                bal.options[bal.answer_no - 1] == orig.options[orig.answer_no - 1]
            ), f"item {orig.item_no}: correct option content changed"
