"""Validator tests for maieutica schemas (T005-T011, spec 009).

TDD: these tests are written before implementation so they are initially
RED and turn GREEN once the 6 schemas are implemented.

Positive cases: valid instances construct without error.
Negative cases: invalid instances raise pydantic.ValidationError.
Soft-flag cases: boundary violations construct successfully but flip bool flags.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_SEM = "2026-1"
_COURSE = "anatomy-physiology"


def _base_textbook_evidence(**overrides: object) -> dict:
    base: dict = {
        "chunk_id": "ch01-s01-001",
        "source_file": "textbook_ch01.txt",
        "char_start": 10,
        "char_end": 50,
        "line": 15,
        "found_text": "세포막은 인지질 이중층으로 구성",
        "search_term": "세포막",
        "status": "확인",
    }
    base.update(overrides)
    return base


def _base_generation_spec(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "week": 1,
        "chapter_no": 1,
        "chapter": "1장 세포의 구조",
        "quiz_count": 20,
        "formative_count": 3,
    }
    base.update(overrides)
    return base


def _base_leap_explanation(**overrides: object) -> dict:
    base: dict = {
        "text": "세포막의 선택적 투과성은 다음 장에서 다루는 삼투압 조절과 직결됩니다.",
    }
    base.update(overrides)
    return base


# 30–50 char options (all exactly 35 chars with spaces counted)
_GOOD_OPTIONS = [
    "인지질 이중층이 세포막의 주요 성분이다",       # ≥30 chars
    "단백질은 세포막에서 수송 역할을 한다",          # ≥30 chars
    "콜레스테롤은 막 유동성을 조절한다",             # ≥30 chars
    "탄수화물은 당사슬 형태로 극소량 존재한다",      # ≥30 chars
    "핵산은 세포막 구성 성분이 아니다고 알려짐",     # ≥30 chars
]

# Each option is short (25 chars) to trigger option_length_ok=False
_SHORT_OPTIONS = [
    "인지질 이중층 세포막 구성",    # < 30 chars
    "단백질 수송 역할 존재함",      # < 30 chars
    "콜레스테롤 막 유동성 조절",    # < 30 chars
    "탄수화물 당사슬 극소량만",     # < 30 chars
    "핵산 세포막 성분 아니다",      # < 30 chars
]

_WRONG_EXPL_OK = "오답을 선택한 학생들은 세포막 구성 성분을 혼동하였습니다. 인지질이 핵심입니다."
_WRONG_EXPL_LONG = "오" * 201  # 201 chars — exceeds soft limit

_LEAP_TEXT_OK = "세포막의 선택적 투과성은 삼투압 조절과 직결됩니다."
_LEAP_TEXT_LONG = "도" * 201  # 201 chars — exceeds soft limit


def _base_quiz_item(**overrides: object) -> dict:
    from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation
    from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

    leap = LeapExplanation(text=_LEAP_TEXT_OK)
    evidence = MaieuticaTextbookEvidence(**_base_textbook_evidence())
    combined = f"{_WRONG_EXPL_OK} ─ 도약 ─ {_LEAP_TEXT_OK}"
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "item_no": 1,
        "week": 1,
        "chapter_no": 1,
        "chapter": "1장 세포의 구조",
        "section": "1.1 세포막",
        "key_concept": "세포막 구조",
        "question_type": "지식축적",
        "difficulty": "중",
        "stem_polarity": "긍정형",
        "text": "세포막의 주요 구성 요소는 무엇인가?",
        "options": _GOOD_OPTIONS,
        "answer_no": 1,
        "option_evidence": ["근거1", "근거2", "근거3", "근거4", "근거5"],
        "wrong_explanation": _WRONG_EXPL_OK,
        "leap": leap,
        "textbook_evidence": evidence,
        "answer_explanation_combined": combined,
        "option_length_ok": True,
        "explanation_length_ok": True,
        "duplicate_flag": False,
        "review_note": "",
        "adoption_status": "생성",
        "note": None,
    }
    base.update(overrides)
    return base


def _base_formative_item(**overrides: object) -> dict:
    from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

    evidence = MaieuticaTextbookEvidence(**_base_textbook_evidence())
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "no": 1,
        "chapter_no": 1,
        "topic": "세포막",
        "question": "세포막의 선택적 투과성 원리를 설명하시오.",
        "limit": "200자 내외",
        "model_answer": "인지질 이중층의 소수성/친수성 배열로 특정 물질만 통과시킨다.",
        "purpose": "세포막 원리 이해 확인",
        "keywords": ["세포막", "선택적 투과성", "인지질"],
        "rubric_high": "소수성/친수성 이중층 원리와 선택적 투과성 모두 정확히 서술",
        "rubric_mid": "선택적 투과성 언급하나 원리 설명 불완전",
        "rubric_low": "세포막 관련 내용이나 원리 설명 없음",
        "support_high": "다음 장 삼투압 조절과 연결 심화 탐구 권장",
        "support_mid": "인지질 이중층 구조 복습 후 재시도",
        "support_low": "세포막 기본 구조 그림 자료로 재학습",
        "textbook_evidence": evidence,
        "review_note": "",
        "adoption_status": "생성",
    }
    base.update(overrides)
    return base


def _base_manifest(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "week": 1,
        "chapter_no": 1,
        "chapter": "1장 세포의 구조",
        "input_hashes": {"textbook_ch01.txt": "abc123"},
        "config_ids": {"generation_spec": "gs-001", "curriculum_map": "cm-001"},
        "generated_at": "2026-06-13T09:00:00+09:00",
        "llm_backend": "subscription",
        "llm_model": "claude-opus-4-5",
        "cache_hit_rate": 0.80,
        "quiz_count": 20,
        "formative_count": 3,
        "answer_no_distribution": {1: 4, 2: 4, 3: 4, 4: 4, 5: 4},
        "stem_polarity_breakdown": {"부정형": 5, "긍정형": 15},
        "difficulty_breakdown": {"상": 5, "중": 10, "하": 5},
        "groundedness": {"확인": 18, "미확인": 2},
        "option_length_violations": 0,
        "explanation_length_violations": 0,
    }
    base.update(overrides)
    return base


# ===========================================================================
# T005: MaieuticaTextbookEvidence
# ===========================================================================


class TestMaieuticaTextbookEvidence:
    """Tests for maieutica.TextbookEvidence (frozen, extra=forbid)."""

    def test_positive_confirmed_with_all_fields(self) -> None:
        """status='확인' with chunk_id + found_text constructs successfully."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        MaieuticaTextbookEvidence(**_base_textbook_evidence())

    def test_positive_confirmed_with_char_range(self) -> None:
        """status='확인' with chunk_id + char_start/char_end only (no found_text)."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        MaieuticaTextbookEvidence(
            chunk_id="ch01-s01-001",
            source_file="textbook_ch01.txt",
            char_start=10,
            char_end=50,
            status="확인",
        )

    def test_positive_unconfirmed_minimal(self) -> None:
        """status='미확인' with only chunk_id + source_file is valid."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        MaieuticaTextbookEvidence(
            chunk_id="ch01-s01-002",
            source_file="textbook_ch01.txt",
            status="미확인",
        )

    def test_positive_char_end_equals_char_start(self) -> None:
        """char_end == char_start is valid (single-char range)."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        MaieuticaTextbookEvidence(**_base_textbook_evidence(char_start=20, char_end=20))

    def test_negative_char_end_before_char_start(self) -> None:
        """char_end < char_start → ValidationError."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        with pytest.raises(ValidationError):
            MaieuticaTextbookEvidence(**_base_textbook_evidence(char_start=50, char_end=10))

    def test_negative_confirmed_no_evidence(self) -> None:
        """status='확인' without chunk_id or found_text/char range → ValidationError."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        with pytest.raises(ValidationError):
            MaieuticaTextbookEvidence(
                chunk_id=None,
                source_file="textbook_ch01.txt",
                status="확인",
            )

    def test_negative_confirmed_chunk_id_but_no_found_text_or_char(self) -> None:
        """status='확인' with chunk_id but no found_text and no char_start/end → ValidationError."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        with pytest.raises(ValidationError):
            MaieuticaTextbookEvidence(
                chunk_id="ch01-s01-001",
                source_file="textbook_ch01.txt",
                status="확인",
            )

    def test_negative_invalid_status(self) -> None:
        """status must be '확인' or '미확인'."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        with pytest.raises(ValidationError):
            MaieuticaTextbookEvidence(**_base_textbook_evidence(status="pending"))

    def test_negative_extra_field(self) -> None:
        """extra='forbid' rejects unknown fields."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        with pytest.raises(ValidationError):
            MaieuticaTextbookEvidence(**_base_textbook_evidence(bad_field="x"))

    def test_positive_frozen(self) -> None:
        """Frozen model rejects attribute mutation."""
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        ev = MaieuticaTextbookEvidence(**_base_textbook_evidence())
        with pytest.raises(Exception):
            ev.status = "미확인"  # type: ignore[misc]


# ===========================================================================
# T006: MaieuticaGenerationSpec
# ===========================================================================


class TestMaieuticaGenerationSpec:
    """Tests for MaieuticaGenerationSpec."""

    def test_positive_valid_explicit(self) -> None:
        """All fields provided explicitly — constructs without error."""
        from paideia_shared.schemas.maieutica.maieutica_generation_spec import MaieuticaGenerationSpec

        MaieuticaGenerationSpec(**_base_generation_spec())

    def test_positive_defaults(self) -> None:
        """Omitting quiz_count and formative_count applies defaults 20 and 3."""
        from paideia_shared.schemas.maieutica.maieutica_generation_spec import MaieuticaGenerationSpec

        spec = MaieuticaGenerationSpec(
            semester=_SEM,
            course_slug=_COURSE,
            week=1,
            chapter_no=1,
            chapter="1장 세포의 구조",
        )
        assert spec.quiz_count == 20
        assert spec.formative_count == 3

    def test_negative_week_zero(self) -> None:
        """week=0 < 1 → ValidationError."""
        from paideia_shared.schemas.maieutica.maieutica_generation_spec import MaieuticaGenerationSpec

        with pytest.raises(ValidationError):
            MaieuticaGenerationSpec(**_base_generation_spec(week=0))

    def test_negative_chapter_no_zero(self) -> None:
        """chapter_no=0 < 1 → ValidationError."""
        from paideia_shared.schemas.maieutica.maieutica_generation_spec import MaieuticaGenerationSpec

        with pytest.raises(ValidationError):
            MaieuticaGenerationSpec(**_base_generation_spec(chapter_no=0))

    def test_negative_quiz_count_zero(self) -> None:
        """quiz_count=0 < 1 → ValidationError."""
        from paideia_shared.schemas.maieutica.maieutica_generation_spec import MaieuticaGenerationSpec

        with pytest.raises(ValidationError):
            MaieuticaGenerationSpec(**_base_generation_spec(quiz_count=0))

    def test_negative_formative_count_zero(self) -> None:
        """formative_count=0 < 1 → ValidationError."""
        from paideia_shared.schemas.maieutica.maieutica_generation_spec import MaieuticaGenerationSpec

        with pytest.raises(ValidationError):
            MaieuticaGenerationSpec(**_base_generation_spec(formative_count=0))

    def test_negative_extra_field(self) -> None:
        """extra='forbid' rejects unknown fields."""
        from paideia_shared.schemas.maieutica.maieutica_generation_spec import MaieuticaGenerationSpec

        with pytest.raises(ValidationError):
            MaieuticaGenerationSpec(**_base_generation_spec(unexpected="x"))


# ===========================================================================
# T007: LeapExplanation
# ===========================================================================


class TestLeapExplanation:
    """Tests for LeapExplanation — no hard length limit, only soft."""

    def test_positive_valid(self) -> None:
        """Short leap explanation constructs successfully."""
        from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation

        LeapExplanation(**_base_leap_explanation())

    def test_positive_with_evidence(self) -> None:
        """Optional textbook_evidence field accepted."""
        from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation
        from paideia_shared.schemas.maieutica.textbook_evidence import MaieuticaTextbookEvidence

        ev = MaieuticaTextbookEvidence(**_base_textbook_evidence())
        LeapExplanation(text=_LEAP_TEXT_OK, textbook_evidence=ev)

    def test_positive_long_text_does_not_raise(self) -> None:
        """text > 200 chars is NOT a hard error (soft flag only — parent QuizItemCandidate flags it)."""
        from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation

        # Should construct without error
        LeapExplanation(text="도약설명" * 60)  # >> 200 chars

    def test_negative_extra_field(self) -> None:
        """extra='forbid' rejects unknown fields."""
        from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation

        with pytest.raises(ValidationError):
            LeapExplanation(**_base_leap_explanation(bad="x"))


# ===========================================================================
# T008: QuizItemCandidate
# ===========================================================================


class TestQuizItemCandidate:
    """Tests for QuizItemCandidate — hard invariants + soft flags."""

    def test_positive_valid_all_ok(self) -> None:
        """Valid item with options in 30–50 range and short explanations."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        item = QuizItemCandidate(**_base_quiz_item())
        assert item.option_length_ok is True
        assert item.explanation_length_ok is True

    def test_positive_short_option_constructs_with_flag_false(self) -> None:
        """Options with <30 chars cause option_length_ok=False but no exception."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        # Override options with short ones — caller also needs to pass matching combined
        leap_text = _LEAP_TEXT_OK
        wrong = _WRONG_EXPL_OK
        combined = f"{wrong} ─ 도약 ─ {leap_text}"
        item = QuizItemCandidate(
            **_base_quiz_item(
                options=_SHORT_OPTIONS,
                option_length_ok=False,
                answer_explanation_combined=combined,
            )
        )
        assert item.option_length_ok is False

    def test_positive_long_wrong_explanation_constructs_with_flag_false(self) -> None:
        """wrong_explanation > 200 chars: explanation_length_ok=False, no exception."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate
        from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation

        leap = LeapExplanation(text=_LEAP_TEXT_OK)
        combined = f"{_WRONG_EXPL_LONG} ─ 도약 ─ {_LEAP_TEXT_OK}"
        item = QuizItemCandidate(
            **_base_quiz_item(
                wrong_explanation=_WRONG_EXPL_LONG,
                leap=leap,
                answer_explanation_combined=combined,
                explanation_length_ok=False,
            )
        )
        assert item.explanation_length_ok is False

    def test_positive_answer_explanation_combined_correct(self) -> None:
        """answer_explanation_combined must equal '{wrong} ─ 도약 ─ {leap.text}'."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        item = QuizItemCandidate(**_base_quiz_item())
        expected = f"{_WRONG_EXPL_OK} ─ 도약 ─ {_LEAP_TEXT_OK}"
        assert item.answer_explanation_combined == expected

    def test_negative_options_len_4(self) -> None:
        """len(options) == 4 → ValidationError."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        with pytest.raises(ValidationError):
            QuizItemCandidate(**_base_quiz_item(options=_GOOD_OPTIONS[:4]))

    def test_negative_options_len_6(self) -> None:
        """len(options) == 6 → ValidationError."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        with pytest.raises(ValidationError):
            QuizItemCandidate(**_base_quiz_item(options=_GOOD_OPTIONS + ["extra"]))

    def test_negative_answer_no_zero(self) -> None:
        """answer_no=0 < 1 → ValidationError."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        with pytest.raises(ValidationError):
            QuizItemCandidate(**_base_quiz_item(answer_no=0))

    def test_negative_answer_no_six(self) -> None:
        """answer_no=6 > 5 → ValidationError."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        with pytest.raises(ValidationError):
            QuizItemCandidate(**_base_quiz_item(answer_no=6))

    def test_negative_option_evidence_len_4(self) -> None:
        """len(option_evidence) == 4 → ValidationError."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        with pytest.raises(ValidationError):
            QuizItemCandidate(**_base_quiz_item(option_evidence=["근거1", "근거2", "근거3", "근거4"]))

    def test_negative_answer_explanation_combined_mismatch(self) -> None:
        """answer_explanation_combined != folded form → ValidationError."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        with pytest.raises(ValidationError):
            QuizItemCandidate(
                **_base_quiz_item(answer_explanation_combined="잘못된 결합 텍스트")
            )

    def test_negative_invalid_adoption_status(self) -> None:
        """adoption_status='draft' → ValidationError."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        with pytest.raises(ValidationError):
            QuizItemCandidate(**_base_quiz_item(adoption_status="draft"))

    def test_negative_invalid_difficulty(self) -> None:
        """difficulty='easy' → ValidationError (must be '상'/'중'/'하')."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        with pytest.raises(ValidationError):
            QuizItemCandidate(**_base_quiz_item(difficulty="easy"))

    def test_positive_difficulty_literals(self) -> None:
        """All three difficulty values '상', '중', '하' are accepted."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        for diff in ("상", "중", "하"):
            QuizItemCandidate(**_base_quiz_item(difficulty=diff))

    def test_positive_default_adoption_status(self) -> None:
        """adoption_status defaults to '생성'."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        item = QuizItemCandidate(**_base_quiz_item())
        assert item.adoption_status == "생성"

    def test_negative_extra_field(self) -> None:
        """extra='forbid' rejects unknown fields."""
        from paideia_shared.schemas.maieutica.quiz_item_candidate import QuizItemCandidate

        with pytest.raises(ValidationError):
            QuizItemCandidate(**_base_quiz_item(bad_key="x"))


# ===========================================================================
# T009: FormativeItemCandidate
# ===========================================================================


class TestFormativeItemCandidate:
    """Tests for FormativeItemCandidate."""

    def test_positive_valid(self) -> None:
        """Valid formative item constructs successfully."""
        from paideia_shared.schemas.maieutica.formative_item_candidate import FormativeItemCandidate

        FormativeItemCandidate(**_base_formative_item())

    def test_positive_no_evidence(self) -> None:
        """textbook_evidence=None is valid."""
        from paideia_shared.schemas.maieutica.formative_item_candidate import FormativeItemCandidate

        FormativeItemCandidate(**_base_formative_item(textbook_evidence=None))

    def test_positive_default_adoption_status(self) -> None:
        """adoption_status defaults to '생성'."""
        from paideia_shared.schemas.maieutica.formative_item_candidate import FormativeItemCandidate

        item = FormativeItemCandidate(**_base_formative_item())
        assert item.adoption_status == "생성"

    def test_positive_empty_keywords(self) -> None:
        """keywords=[] is valid."""
        from paideia_shared.schemas.maieutica.formative_item_candidate import FormativeItemCandidate

        FormativeItemCandidate(**_base_formative_item(keywords=[]))

    def test_negative_no_zero(self) -> None:
        """no=0 < 1 → ValidationError."""
        from paideia_shared.schemas.maieutica.formative_item_candidate import FormativeItemCandidate

        with pytest.raises(ValidationError):
            FormativeItemCandidate(**_base_formative_item(no=0))

    def test_negative_invalid_adoption_status(self) -> None:
        """adoption_status='pending' → ValidationError."""
        from paideia_shared.schemas.maieutica.formative_item_candidate import FormativeItemCandidate

        with pytest.raises(ValidationError):
            FormativeItemCandidate(**_base_formative_item(adoption_status="pending"))

    def test_negative_extra_field(self) -> None:
        """extra='forbid' rejects unknown fields."""
        from paideia_shared.schemas.maieutica.formative_item_candidate import FormativeItemCandidate

        with pytest.raises(ValidationError):
            FormativeItemCandidate(**_base_formative_item(garbage="x"))


# ===========================================================================
# T010: MaieuticaManifest
# ===========================================================================


class TestMaieuticaManifest:
    """Tests for MaieuticaManifest."""

    def test_positive_valid(self) -> None:
        """Valid manifest constructs successfully."""
        from paideia_shared.schemas.maieutica.maieutica_manifest import MaieuticaManifest

        MaieuticaManifest(**_base_manifest())

    def test_positive_dry_run_backend(self) -> None:
        """none(dry-run) is a valid llm_backend value."""
        from paideia_shared.schemas.maieutica.maieutica_manifest import MaieuticaManifest

        MaieuticaManifest(**_base_manifest(llm_backend="none(dry-run)", llm_model=None))

    def test_positive_no_cache_hit_rate(self) -> None:
        """cache_hit_rate=None is valid."""
        from paideia_shared.schemas.maieutica.maieutica_manifest import MaieuticaManifest

        MaieuticaManifest(**_base_manifest(cache_hit_rate=None))

    def test_positive_violation_counters_are_int(self) -> None:
        """option_length_violations and explanation_length_violations are ints."""
        from paideia_shared.schemas.maieutica.maieutica_manifest import MaieuticaManifest

        m = MaieuticaManifest(**_base_manifest(option_length_violations=3, explanation_length_violations=1))
        assert m.option_length_violations == 3
        assert m.explanation_length_violations == 1

    def test_negative_invalid_llm_backend(self) -> None:
        """llm_backend='local' → ValidationError."""
        from paideia_shared.schemas.maieutica.maieutica_manifest import MaieuticaManifest

        with pytest.raises(ValidationError):
            MaieuticaManifest(**_base_manifest(llm_backend="local"))

    def test_negative_extra_field(self) -> None:
        """extra='forbid' rejects unknown fields."""
        from paideia_shared.schemas.maieutica.maieutica_manifest import MaieuticaManifest

        with pytest.raises(ValidationError):
            MaieuticaManifest(**_base_manifest(oops="x"))


# ===========================================================================
# T011: __init__.py exports
# ===========================================================================


class TestMaieuticaSchemaExports:
    """Verify all 6 new maieutica schemas are importable from paideia_shared.schemas."""

    def test_maieutica_textbook_evidence_exported(self) -> None:
        from paideia_shared.schemas import MaieuticaTextbookEvidence as _  # noqa: F401

    def test_maieutica_generation_spec_exported(self) -> None:
        from paideia_shared.schemas import MaieuticaGenerationSpec as _  # noqa: F401

    def test_leap_explanation_exported(self) -> None:
        from paideia_shared.schemas import LeapExplanation as _  # noqa: F401

    def test_quiz_item_candidate_exported(self) -> None:
        from paideia_shared.schemas import QuizItemCandidate as _  # noqa: F401

    def test_formative_item_candidate_exported(self) -> None:
        from paideia_shared.schemas import FormativeItemCandidate as _  # noqa: F401

    def test_maieutica_manifest_exported(self) -> None:
        from paideia_shared.schemas import MaieuticaManifest as _  # noqa: F401
