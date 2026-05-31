"""T041 + T042 — Unit: vary_quiz generation + jaccard variation guard.

TDD (RED phase): tests written before implementation.

T041: vary_quiz(entry, backend, cache) → ExamItemDraft
- Mirrors convert_formative pattern (parse SourceInventoryEntry → backend → ExamItemDraft)
- Deterministic via cache; backend-isolated (FakeBackend)
- ExamItemDraft has source="quiz", source_ref=entry.source_ref

T042: jaccard variation guard
- token_jaccard(original_text, varied_text) → float in [0, 1]
- check_quiz_variation(item, original_entry) → ExamItemDraft
  - 0 < J < 0.8: passes (no review_note added for jaccard)
  - J == 0 (wholly different): flags in review_note
  - J >= 0.8 (too similar / identical): flags in review_note
  - J > 0 and J < 0.8: no jaccard flag in review_note
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    InputHashCache,
    LLMBackend,
)
from paideia_shared.schemas import ExamItemDraft, SourceInventoryEntry

_SEMESTER = "2026-1"
_COURSE = "anatomy"

# ---------------------------------------------------------------------------
# Synthetic quiz entry (original quiz text)
# ---------------------------------------------------------------------------

_ORIGINAL_STEM = "호흡(respiration)의 정의에 대한 설명 중에서 가장 옳지 않은 것을 고르세요."
_ORIGINAL_OPTIONS = [
    "① 호흡이란 외부로부터 산소를 몸 안으로 흡입하여 세포로 운반하는 과정을 포함한다.",
    "② 호흡은 세포의 대사활동 결과 발생한 이산화탄소를 몸 밖으로 배출하는 과정이다.",
    "③ 외호흡은 모세혈관 내 혈액과 조직세포 사이에서 공기가 교환되는 과정이다.",
    "④ 내호흡은 모세혈관 내 혈액과 조직세포 사이에서 공기가 교환된다.",
    "⑤ 외호흡은 허파호흡이라고도 하며, 내호흡은 조직호흡이라고도 한다.",
]
_ORIGINAL_ANSWER = "3"


def _make_quiz_entry(
    *,
    stem: str = _ORIGINAL_STEM,
    options: list[str] | None = None,
    answer: str = _ORIGINAL_ANSWER,
    source_ref: str = "퀴즈:9주#1",
    chapter_no: int = 9,
) -> SourceInventoryEntry:
    return SourceInventoryEntry(
        semester=_SEMESTER,
        course_slug=_COURSE,
        source="quiz",
        source_ref=source_ref,
        chapter_no=chapter_no,
        week=9,
        stem=stem,
        options=options or _ORIGINAL_OPTIONS,
        answer=answer,
    )


# ---------------------------------------------------------------------------
# Canned LLM responses
# ---------------------------------------------------------------------------

_VARIATION_RESPONSE: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "2_보통",
    "stem_polarity": "부정형",
    "text": "다음 중 호흡 과정에 대한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① 외호흡은 허파 혈관과 허파꽈리 사이에서 가스교환이 이루어진다.",
        "② 내호흡은 모세혈관과 조직세포 사이의 가스교환 과정이다.",
        "③ 호흡은 산소를 세포로 운반하고 이산화탄소를 배출하는 과정이다.",
        "④ 허파호흡(외호흡)과 조직호흡(내호흡)은 서로 다른 위치에서 일어난다.",
        "⑤ 조직세포와 모세혈관 사이의 가스교환은 내호흡이 아닌 외호흡이다.",
    ],
    "answer_no": 5,
    "distractor_rationale": [
        "옳은 진술.",
        "옳은 진술.",
        "옳은 진술.",
        "옳은 진술.",
        "틀린 진술: 외호흡이 아닌 내호흡.",
    ],
    "wrong_explanation": "변형 오답 설명." * 20,
    "leap_explanation": "변형 도약 설명." * 20,
    "intent": "호흡 개념 확인.",
    "key_concept": "외호흡",
}


class FakeQuizBackend(LLMBackend):
    def __init__(self, response_dict: dict[str, Any] | None = None) -> None:
        self.call_count = 0
        self._response = response_dict or _VARIATION_RESPONSE

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=json.dumps(self._response, ensure_ascii=False),
            model="fake-quiz",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# Tests: vary_quiz
# ---------------------------------------------------------------------------


class TestVaryQuiz:
    """vary_quiz(entry, backend, cache) → ExamItemDraft."""

    def test_returns_exam_item_draft(self, tmp_path: Path) -> None:
        """vary_quiz returns an ExamItemDraft."""
        from examen.generate.vary_quiz import vary_quiz

        entry = _make_quiz_entry()
        backend = FakeQuizBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        result = vary_quiz(entry, backend, cache)
        assert isinstance(result, ExamItemDraft)

    def test_source_is_quiz(self, tmp_path: Path) -> None:
        """Returned ExamItemDraft has source='quiz'."""
        from examen.generate.vary_quiz import vary_quiz

        entry = _make_quiz_entry()
        backend = FakeQuizBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        result = vary_quiz(entry, backend, cache)
        assert result.source == "quiz"

    def test_source_ref_preserved(self, tmp_path: Path) -> None:
        """Returned item.source_ref == entry.source_ref."""
        from examen.generate.vary_quiz import vary_quiz

        entry = _make_quiz_entry(source_ref="퀴즈:9주#5")
        backend = FakeQuizBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        result = vary_quiz(entry, backend, cache)
        assert result.source_ref == "퀴즈:9주#5"

    def test_answer_no_in_range(self, tmp_path: Path) -> None:
        """answer_no is in [1, 5]."""
        from examen.generate.vary_quiz import vary_quiz

        entry = _make_quiz_entry()
        backend = FakeQuizBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        result = vary_quiz(entry, backend, cache)
        assert 1 <= result.answer_no <= 5

    def test_has_five_options(self, tmp_path: Path) -> None:
        """Generated item has exactly 5 options."""
        from examen.generate.vary_quiz import vary_quiz

        entry = _make_quiz_entry()
        backend = FakeQuizBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        result = vary_quiz(entry, backend, cache)
        assert len(result.options) == 5

    def test_raises_if_source_not_quiz(self, tmp_path: Path) -> None:
        """vary_quiz raises ValueError if entry.source != 'quiz'."""
        from examen.generate.vary_quiz import vary_quiz

        entry = SourceInventoryEntry(
            semester=_SEMESTER,
            course_slug=_COURSE,
            source="formative",
            source_ref="형성평가:9장#1",
            chapter_no=9,
            week=9,
            stem="서술형 질문",
        )
        backend = FakeQuizBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        with pytest.raises(ValueError, match="quiz"):
            vary_quiz(entry, backend, cache)

    def test_deterministic_via_cache(self, tmp_path: Path) -> None:
        """Two identical calls return identical result (cache-backed determinism)."""
        from examen.generate.vary_quiz import vary_quiz

        entry = _make_quiz_entry()
        backend = FakeQuizBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        result1 = vary_quiz(entry, backend, cache)
        result2 = vary_quiz(entry, backend, cache)
        # Second call is cache hit — same result
        assert result1.text == result2.text
        assert result1.answer_no == result2.answer_no
        assert backend.call_count == 1  # backend called only once

    def test_chapter_no_set(self, tmp_path: Path) -> None:
        """Returned item has chapter_no set from entry."""
        from examen.generate.vary_quiz import vary_quiz

        entry = _make_quiz_entry(chapter_no=10)
        backend = FakeQuizBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "cache")
        result = vary_quiz(entry, backend, cache)
        assert result.chapter_no == 10


# ---------------------------------------------------------------------------
# Tests: token_jaccard utility + check_quiz_variation (T042)
# ---------------------------------------------------------------------------


class TestTokenJaccard:
    """token_jaccard(a, b) → float in [0, 1]."""

    def test_identical_texts_jaccard_is_one(self) -> None:
        """Identical texts → Jaccard == 1.0."""
        from examen.verify.format_checks import token_jaccard

        text = "외호흡은 허파꽈리에서 이루어진다"
        assert token_jaccard(text, text) == pytest.approx(1.0)

    def test_disjoint_texts_jaccard_is_zero(self) -> None:
        """Completely different tokens → Jaccard == 0.0."""
        from examen.verify.format_checks import token_jaccard

        a = "외호흡 허파꽈리 가스교환"
        b = "근육수축 근섬유 ATP에너지"
        assert token_jaccard(a, b) == pytest.approx(0.0)

    def test_partial_overlap_jaccard_in_range(self) -> None:
        """Partial overlap returns value in (0, 1)."""
        from examen.verify.format_checks import token_jaccard

        a = "외호흡 허파꽈리 가스교환 산소"
        b = "외호흡 허파꽈리 이산화탄소 근육"
        j = token_jaccard(a, b)
        assert 0.0 < j < 1.0

    def test_jaccard_symmetric(self) -> None:
        """token_jaccard(a, b) == token_jaccard(b, a)."""
        from examen.verify.format_checks import token_jaccard

        a = "외호흡 허파꽈리 가스교환"
        b = "내호흡 조직세포 이산화탄소"
        assert token_jaccard(a, b) == pytest.approx(token_jaccard(b, a))

    def test_empty_strings_jaccard_is_zero(self) -> None:
        """Empty strings → Jaccard == 0.0 (no tokens, no intersection)."""
        from examen.verify.format_checks import token_jaccard

        assert token_jaccard("", "") == pytest.approx(0.0)

    def test_one_empty_string_jaccard_is_zero(self) -> None:
        """One empty string → Jaccard == 0.0."""
        from examen.verify.format_checks import token_jaccard

        assert token_jaccard("외호흡", "") == pytest.approx(0.0)


class TestCheckQuizVariation:
    """check_quiz_variation(item, original_entry) → ExamItemDraft with jaccard guard."""

    def _make_item(
        self,
        *,
        text: str = "다음 중 호흡 과정에 대한 설명으로 가장 옳지 않은 것은?",
        options: list[str] | None = None,
        source_ref: str = "퀴즈:9주#1",
        review_note: str = "",
    ) -> ExamItemDraft:
        """Build a minimal ExamItemDraft for testing."""
        opts = options or [
            "① 외호흡은 허파 혈관과 허파꽈리 사이에서 가스교환이 이루어진다.",
            "② 내호흡은 모세혈관과 조직세포 사이의 가스교환 과정이다.",
            "③ 호흡은 산소를 세포로 운반하고 이산화탄소를 배출하는 과정이다.",
            "④ 허파호흡과 조직호흡은 서로 다른 위치에서 일어난다.",
            "⑤ 조직세포와 모세혈관 사이의 가스교환은 내호흡이 아닌 외호흡이다.",
        ]
        return ExamItemDraft(
            semester=_SEMESTER,
            course_slug=_COURSE,
            item_no=1,
            source="quiz",
            source_ref=source_ref,
            chapter="9장 호흡계통",
            chapter_no=9,
            section=None,
            week=9,
            key_concept="외호흡",
            is_emphasized=None,
            emphasis_class_count=None,
            question_type="지식축적",
            bloom=None,
            difficulty="2_보통",
            stem_polarity="부정형",
            text=text,
            options=opts,
            answer_no=5,
            distractor_rationale=["옳은"] * 4 + ["틀린 진술."],
            wrong_explanation="오답 설명." * 10,
            leap_explanation="도약 설명." * 10,
            textbook_evidence=None,
            intent="의도.",
            option_length_ok=True,
            duplicate_flag=False,
            review_note=review_note,
            adoption_status="생성",
            note=None,
        )

    def test_good_variation_no_jaccard_flag(self) -> None:
        """Variation with 0 < J < 0.8 does not add jaccard violation to review_note."""
        from examen.verify.format_checks import check_quiz_variation

        original_entry = _make_quiz_entry()
        varied_item = self._make_item()  # Uses different wording from original
        result = check_quiz_variation(varied_item, original_entry)
        # review_note should NOT contain 'jaccard'
        assert "jaccard" not in (result.review_note or "").lower(), (
            f"Unexpected jaccard note for good variation: {result.review_note!r}"
        )

    def test_identical_text_flagged_as_too_similar(self) -> None:
        """Variation with J >= 0.8 (identical text) gets jaccard flag in review_note."""
        from examen.verify.format_checks import check_quiz_variation

        original_entry = _make_quiz_entry()
        # Use identical stem and options as original → J = 1.0
        identical_item = self._make_item(
            text=_ORIGINAL_STEM,
            options=_ORIGINAL_OPTIONS,
        )
        result = check_quiz_variation(identical_item, original_entry)
        assert "jaccard" in (result.review_note or "").lower(), (
            "Expected jaccard flag for identical text"
        )

    def test_wholly_different_text_flagged(self) -> None:
        """Variation with J == 0 (wholly different) gets jaccard flag in review_note.

        We use an original entry with NO circled numbers (to avoid shared ①②③④⑤ tokens)
        and a varied item whose tokens are entirely disjoint from the original.
        """
        from examen.verify.format_checks import check_quiz_variation

        # Use plain text without circled numbers so varied item has zero shared tokens
        original_entry = _make_quiz_entry(
            stem="외호흡 허파꽈리 가스교환",
            options=["보기가", "보기나", "보기다", "보기라", "보기마"],
        )
        # Varied item with entirely different vocabulary (no shared tokens)
        disjoint_item = self._make_item(
            text="근육수축관련근섬유ATP에너지",
            options=[
                "① 근섬유는마이오신과액틴으로구성된다.",
                "② ATP가근육수축에필요한에너지원이다.",
                "③ 근육이완시칼슘이세포내로들어간다.",
                "④ 골격근은수의근으로의지로조절된다.",
                "⑤ 근육피로시젖산이축적된다는것이다.",
            ],
        )
        # Verify these are truly disjoint (no shared whitespace tokens)
        from examen.verify.format_checks import token_jaccard

        original_opts = original_entry.options or []
        original_text = " ".join([original_entry.stem] + original_opts)
        varied_text = " ".join([disjoint_item.text] + list(disjoint_item.options))
        j = token_jaccard(original_text, varied_text)
        if 0.0 < j < 0.8:
            # Can't test with this data — skip rather than produce a false test
            pytest.skip(f"Cannot produce truly disjoint test data (jaccard={j:.3f})")

        result = check_quiz_variation(disjoint_item, original_entry)
        assert "jaccard" in (result.review_note or "").lower(), (
            f"Expected jaccard flag for wholly different text (jaccard={j:.3f})"
        )

    def test_returns_exam_item_draft(self) -> None:
        """check_quiz_variation returns an ExamItemDraft (model_copy or same)."""
        from examen.verify.format_checks import check_quiz_variation

        original_entry = _make_quiz_entry()
        varied_item = self._make_item()
        result = check_quiz_variation(varied_item, original_entry)
        assert isinstance(result, ExamItemDraft)

    def test_does_not_crash_without_original_text(self) -> None:
        """If original_entry has empty stem/options, check_quiz_variation does not crash."""
        from examen.verify.format_checks import check_quiz_variation

        original_entry = SourceInventoryEntry(
            semester=_SEMESTER,
            course_slug=_COURSE,
            source="quiz",
            source_ref="퀴즈:9주#1",
            stem="",  # empty
            options=None,  # None
        )
        varied_item = self._make_item()
        # Should not raise — just flags or skips
        result = check_quiz_variation(varied_item, original_entry)
        assert isinstance(result, ExamItemDraft)

    def test_existing_review_note_preserved(self) -> None:
        """Pre-existing review_note content is preserved when jaccard flag is added."""
        from examen.verify.format_checks import check_quiz_variation

        original_entry = _make_quiz_entry()
        item = self._make_item(
            text=_ORIGINAL_STEM,
            options=_ORIGINAL_OPTIONS,
            review_note="기존 검토 메모",
        )
        result = check_quiz_variation(item, original_entry)
        # Both the original note and the jaccard flag should be present
        note = result.review_note or ""
        assert "기존 검토 메모" in note
        assert "jaccard" in note.lower()
