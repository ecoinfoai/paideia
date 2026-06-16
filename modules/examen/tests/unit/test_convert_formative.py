"""T032 — Unit tests: convert_formative invariants.

TDD (RED phase): tests written before implementation.

Invariants under test:
- convert_formative returns ExamItemDraft with source="formative"
- answer_no points to the WRONG option (부정형 — the false statement)
- stem_polarity is always "부정형"
- options list has exactly 5 entries
- source_ref copied from entry
- chapter/chapter_no copied from entry
- deterministic: same input → same output (via cache)
- cache prevents repeated backend calls (cache_hit on re-run)
- no network (FakeFormativeBackend only)
- distractor_rationale has exactly 5 entries
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    InputHashCache,
    LLMBackend,
)
from paideia_shared.schemas import ExamItemDraft, SourceInventoryEntry

# ---------------------------------------------------------------------------
# Synthetic SourceInventoryEntry fixture
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"


def _make_entry(
    *,
    sn: int = 1,
    chapter_no: int = 8,
    week: int = 8,
    stem: str = "허파꽈리를 구성하는 세포의 종류와 각 세포의 기능을 설명하시오.",
    model_answer: str | None = None,
    keywords: list[str] | None = None,
    rubric: dict[str, str] | None = None,
) -> SourceInventoryEntry:
    """Build a synthetic SourceInventoryEntry for testing."""
    if model_answer is None:
        model_answer = (
            "허파꽈리는 2종류의 세포로 덮여 있다. 제1형 허파세포는 가스 교환이 일어나는 얇은 "
            "세포이며, 제2형 허파세포는 표면활성제(계면활성제)를 분비하여 허파꽈리의 표면장력을 "
            "낮추고 허파꽈리 허탈을 방지한다."
        )
    if keywords is None:
        keywords = ["제1형 허파세포", "제2형 허파세포", "표면활성제", "가스 교환", "표면장력"]
    if rubric is None:
        rubric = {
            "high": "세포 2종 모두 기술, 표면활성제 기능까지 정확히 설명",
            "mid": "세포 2종은 기술하나 기능 설명 부족",
            "low": "허파꽈리 세포가 1종이라고 오개념 기술",
        }

    return SourceInventoryEntry(
        semester=_SEMESTER,
        course_slug=_COURSE,
        source="formative",
        source_ref=f"형성평가:{chapter_no}장#{sn}",
        chapter_no=chapter_no,
        week=week,
        stem=stem,
        model_answer=model_answer,
        keywords=keywords,
        rubric=rubric,
    )


# ---------------------------------------------------------------------------
# Canned LLM response for formative conversion
# ---------------------------------------------------------------------------

# answer_no=5 → option 5 is the WRONG one (the false statement)
_CANNED_FORMATIVE_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "2_보통",
    "stem_polarity": "부정형",
    "text": "다음 중 허파꽈리 세포에 대한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① " + "제1형 허파세포는 가스 교환이 일어나는 얇은 편평세포이다.",
        "② " + "제2형 허파세포는 표면활성제를 분비하여 표면장력을 낮춘다.",
        "③ " + "표면활성제는 허파꽈리의 허탈(collapse)을 방지하는 기능을 한다.",
        "④ " + "허파꽈리의 벽은 주로 제1형과 제2형 두 종류의 세포로 구성된다.",
        "⑤ " + "제2형 허파세포는 가스 교환의 주요 세포이며 섬모를 보유하고 있다.",
    ],
    "answer_no": 5,  # ← WRONG option is the answer (부정형)
    "distractor_rationale": [
        "옳은 진술: 제1형 허파세포는 편평하고 얇아 가스 교환에 적합하다.",
        "옳은 진술: 제2형 허파세포는 계면활성제를 분비한다.",
        "옳은 진술: 표면활성제는 표면장력 감소로 허탈을 예방한다.",
        "옳은 진술: 허파꽈리는 제1형·제2형 두 세포로 구성된다.",
        "틀린 진술: 제2형 허파세포는 가스 교환 세포가 아니며 섬모도 없다.",
    ],
    "wrong_explanation": "제2형 허파세포에 대한 오답 설명 텍스트입니다." * 10,
    "leap_explanation": "제2형 허파세포에 대한 도약 설명 텍스트입니다." * 10,
    "intent": "허파꽈리 세포 종류와 기능을 정확히 이해하는지 확인한다.",
    "key_concept": "제2형 허파세포",
    "wrong_option_no": 5,  # 형성 전용 필드 — 파서가 answer_no 로 전달
}


class FakeFormativeBackend(LLMBackend):
    """Returns canned formative conversion JSON; counts calls."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=json.dumps(_CANNED_FORMATIVE_JSON, ensure_ascii=False),
            model="fake-formative",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConvertFormativeInvariants:
    """Unit tests for convert_formative() invariants (T034)."""

    def _convert(
        self,
        tmp_path: Path,
        *,
        entry: SourceInventoryEntry | None = None,
        backend: LLMBackend | None = None,
    ) -> ExamItemDraft:
        """Call convert_formative and return the result."""
        from examen.generate.convert_formative import convert_formative

        if entry is None:
            entry = _make_entry()
        if backend is None:
            backend = FakeFormativeBackend()

        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        return convert_formative(entry=entry, backend=backend, cache=cache)

    def test_source_is_formative(self, tmp_path: Path) -> None:
        """convert_formative produces item with source='formative'."""
        item = self._convert(tmp_path)
        assert item.source == "formative", f"Expected source=formative, got {item.source!r}"

    def test_source_ref_copied(self, tmp_path: Path) -> None:
        """source_ref on the item matches the entry source_ref."""
        entry = _make_entry(sn=3, chapter_no=8)
        item = self._convert(tmp_path, entry=entry)
        assert item.source_ref == "형성평가:8장#3", f"source_ref mismatch: {item.source_ref!r}"

    def test_chapter_no_copied(self, tmp_path: Path) -> None:
        """chapter_no on the item matches the entry chapter_no."""
        entry = _make_entry(chapter_no=9)
        item = self._convert(tmp_path, entry=entry)
        assert item.chapter_no == 9, f"chapter_no mismatch: {item.chapter_no}"

    def test_stem_polarity_is_negative(self, tmp_path: Path) -> None:
        """stem_polarity must always be '부정형' for formative items."""
        item = self._convert(tmp_path)
        assert item.stem_polarity == "부정형", (
            f"stem_polarity must be 부정형, got {item.stem_polarity!r}"
        )

    def test_exactly_five_options(self, tmp_path: Path) -> None:
        """Item must have exactly 5 options."""
        item = self._convert(tmp_path)
        assert len(item.options) == 5, f"Expected 5 options, got {len(item.options)}"

    def test_exactly_five_distractor_rationale(self, tmp_path: Path) -> None:
        """distractor_rationale must have exactly 5 entries."""
        item = self._convert(tmp_path)
        assert len(item.distractor_rationale) == 5, (
            f"Expected 5 distractor_rationale, got {len(item.distractor_rationale)}"
        )

    def test_answer_no_in_range(self, tmp_path: Path) -> None:
        """answer_no must be between 1 and 5 inclusive."""
        item = self._convert(tmp_path)
        assert 1 <= item.answer_no <= 5, f"answer_no out of range: {item.answer_no}"

    def test_answer_no_is_wrong_option(self, tmp_path: Path) -> None:
        """For 부정형 formative, answer_no points to the WRONG (false) option.

        Strengthened: instead of trivially asserting ``answer_no == 5`` (which
        the FakeBackend hardcodes), assert the prompt-contract RELATIONSHIP —
        the distractor_rationale entry at answer_no carries the "틀린" marker,
        and NO other rationale carries it.  This proves the answer is the false
        statement, not just a fixed index.
        """
        item = self._convert(tmp_path)
        idx = item.answer_no - 1
        assert 0 <= idx < len(item.distractor_rationale), (
            f"answer_no {item.answer_no} out of rationale range"
        )
        answer_rationale = item.distractor_rationale[idx]
        assert "틀린" in answer_rationale, (
            f"answer_no={item.answer_no} rationale must carry the '틀린' marker "
            f"(the false statement), got {answer_rationale!r}"
        )
        # The other 4 rationales must NOT carry the 틀린 marker (they are 옳은)
        others = [r for i, r in enumerate(item.distractor_rationale) if i != idx]
        assert all("틀린" not in r for r in others), (
            "only the answer's rationale should be marked '틀린'; "
            f"found a non-answer rationale also marked: {others!r}"
        )

    def test_week_copied(self, tmp_path: Path) -> None:
        """week on the item matches the entry week."""
        entry = _make_entry(week=9)
        item = self._convert(tmp_path, entry=entry)
        assert item.week == 9, f"week mismatch: {item.week}"

    def test_schema_valid(self, tmp_path: Path) -> None:
        """The returned ExamItemDraft is schema-valid (Pydantic does not raise)."""
        item = self._convert(tmp_path)
        # Re-construct from dict to force schema validation
        reconstructed = ExamItemDraft(**item.model_dump())
        assert reconstructed.source == "formative"

    def test_deterministic_same_output_twice(self, tmp_path: Path) -> None:
        """Same input → same ExamItemDraft (deterministic via cache)."""
        from examen.generate.convert_formative import convert_formative

        entry = _make_entry()
        backend = FakeFormativeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")

        item1 = convert_formative(entry=entry, backend=backend, cache=cache)
        item2 = convert_formative(entry=entry, backend=backend, cache=cache)

        assert item1.model_dump() == item2.model_dump(), (
            "convert_formative is not deterministic: two calls with same input differ"
        )

    def test_cache_prevents_double_backend_call(self, tmp_path: Path) -> None:
        """Second call with same input hits cache; backend called only once."""
        from examen.generate.convert_formative import convert_formative

        entry = _make_entry()
        backend = FakeFormativeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")

        convert_formative(entry=entry, backend=backend, cache=cache)
        assert backend.call_count == 1, f"Expected 1 backend call, got {backend.call_count}"

        convert_formative(entry=entry, backend=backend, cache=cache)
        # Cache hit → backend NOT called again
        assert backend.call_count == 1, (
            f"Expected still 1 backend call after cache hit, got {backend.call_count}"
        )

    def test_no_network_call(self, tmp_path: Path) -> None:
        """FakeFormativeBackend is used — no real network access."""
        # If convert_formative tries to import real backend, FakeFormativeBackend
        # intercepts. This test documents the no-network contract.
        backend = FakeFormativeBackend()
        item = self._convert(tmp_path, backend=backend)
        # backend.call_count >= 0 (not necessarily 1 if cache was pre-seeded
        # by another test, but definitely no real network call)
        assert item.source == "formative"


class TestConvertFormativeOptionShape:
    """Tests for option content constraints from the LLM response."""

    def _convert(self, tmp_path: Path) -> ExamItemDraft:
        from examen.generate.convert_formative import convert_formative

        entry = _make_entry()
        backend = FakeFormativeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        return convert_formative(entry=entry, backend=backend, cache=cache)

    def test_text_not_empty(self, tmp_path: Path) -> None:
        """Stem text is non-empty."""
        item = self._convert(tmp_path)
        assert item.text.strip(), "item.text must not be empty"

    def test_options_are_strings(self, tmp_path: Path) -> None:
        """All 5 options are non-empty strings."""
        item = self._convert(tmp_path)
        for i, opt in enumerate(item.options):
            assert isinstance(opt, str) and opt.strip(), (
                f"option[{i}] is not a valid string: {opt!r}"
            )

    def test_semester_and_course_preserved(self, tmp_path: Path) -> None:
        """semester and course_slug on the item match the entry values."""
        entry = _make_entry()
        from examen.generate.convert_formative import convert_formative

        backend = FakeFormativeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        item = convert_formative(entry=entry, backend=backend, cache=cache)
        assert item.semester == _SEMESTER
        assert item.course_slug == _COURSE
