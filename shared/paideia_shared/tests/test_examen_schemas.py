"""Validator tests for examen schemas (T004-T011, spec 008).

TDD: these tests must be written before implementation so they are initially
RED and turn GREEN once the 7 schemas are implemented.

Positive cases: valid instances construct without error.
Negative cases: invalid instances raise pydantic.ValidationError with an
appropriate message or code, verifying each constraint is enforced.
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import (
    CurriculumEntry,
    CurriculumMap,
    EmphasisCell,
    ExamenBlueprint,
    ExamenManifest,
    ExamItemDraft,
    SourceInventoryEntry,
    TextbookChunk,
    TextbookEvidence,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_SEM = "2026-1"
_COURSE = "anatomy"


def _base_blueprint(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "exam_name": "2026-1학기 기말고사",
        "total_items": 45,
        "chapters": ["1장", "2장", "3장", "4장", "5장", "6장"],
        "difficulty_targets": {"easy": 0.45, "medium": 0.35, "hard": 0.20},
        "source_mix": {"formative": 10, "quiz": 15, "textbook": 20},
        "quiz_target": 15,
        "answer_key_balance": True,
    }
    base.update(overrides)
    return base


def _base_entry(**overrides: object) -> dict:
    base: dict = {
        "week": 1,
        "chapter": "1장 세포의 구조",
        "chapter_no": 1,
        "subtopic": None,
        "sections": ["세포막", "세포핵"],
    }
    base.update(overrides)
    return base


def _base_curriculum_map(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "entries": [CurriculumEntry(**_base_entry())],
    }
    base.update(overrides)
    return base


def _base_source_inventory(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "source": "formative",
        "source_ref": "형성평가:1장#1",
        "chapter_no": 1,
        "week": 1,
        "stem": "세포막의 주요 기능을 설명하시오.",
        "model_answer": "선택적 투과성을 통해 세포 내외 물질 이동을 조절한다.",
        "keywords": ["세포막", "투과성"],
        "rubric": {"high": "정확", "mid": "부분 정확", "low": "불충분"},
        "options": None,
        "answer": None,
    }
    base.update(overrides)
    return base


def _base_textbook_chunk(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "chunk_id": "ch01-s01-001",
        "chapter_no": 1,
        "chapter": "1장 세포의 구조",
        "section": "1.1 세포막",
        "source_file": "textbook_ch01.txt",
        "line_start": 10,
        "line_end": 25,
        "text": "세포막은 인지질 이중층으로 구성되어 있다.",
        "removed_spans": [],
    }
    base.update(overrides)
    return base


def _base_emphasis_cell(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "chapter_no": 1,
        "section": "1.1 세포막",
        "emphasized_class_count": 3,
        "available_class_count": 3,
        "is_emphasized": True,
        "evidence_refs": ["A반-1차시", "B반-1차시", "C반-1차시"],
    }
    base.update(overrides)
    return base


def _base_textbook_evidence(**overrides: object) -> dict:
    base: dict = {
        "source_file": "textbook_ch01.txt",
        "line": 15,
        "found_text": "세포막은 인지질 이중층으로 구성",
        "status": "확인",
        "search_term": "세포막",
    }
    base.update(overrides)
    return base


def _base_exam_item_draft(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "item_no": 1,
        "source": "textbook",
        "source_ref": None,
        "chapter": "1장 세포의 구조",
        "chapter_no": 1,
        "section": "1.1 세포막",
        "week": 1,
        "key_concept": "세포막 구조",
        "is_emphasized": True,
        "emphasis_class_count": 3,
        "question_type": "지식축적",
        "bloom": "comprehension",
        "difficulty": "1_쉬움",
        "stem_polarity": "긍정형",
        "text": "세포막의 주요 구성 요소는 무엇인가?",
        "options": ["인지질", "단백질", "콜레스테롤", "탄수화물", "핵산"],
        "answer_no": 1,
        "distractor_rationale": [
            "정답: 인지질 이중층이 주요 성분임",
            "단백질도 존재하나 주성분은 아님",
            "콜레스테롤은 보조 성분임",
            "탄수화물은 당사슬 형태로 극소량 존재",
            "핵산은 세포막 구성 성분이 아님",
        ],
        "wrong_explanation": "오답을 선택한 학생들은 세포막의 구성 성분을 혼동하였습니다. " * 6,
        "leap_explanation": "정답을 맞힌 학생들은 세포막의 기본 구조를 잘 이해하고 있습니다. " * 6,
        "textbook_evidence": TextbookEvidence(**_base_textbook_evidence()),
        "intent": "세포막의 주요 구성 성분을 인지하는지 확인",
        "option_length_ok": True,
        "duplicate_flag": False,
        "review_note": "",
        "adoption_status": "생성",
        "note": None,
    }
    base.update(overrides)
    return base


def _base_examen_manifest(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEM,
        "course_slug": _COURSE,
        "exam_name": "2026-1학기 기말고사",
        "input_hashes": {"blueprint.yaml": "abc123", "curriculum_map.yaml": "def456"},
        "config_ids": {"blueprint_id": "bp-001", "curriculum_id": "cm-001"},
        "generated_at": "2026-05-31T12:00:00+09:00",
        "llm_backend": "subscription",
        "llm_model": "claude-opus-4-5",
        "cache_hit_rate": 0.75,
        "item_count": 45,
        "source_breakdown": {"formative": 10, "quiz": 15, "textbook": 20},
        "difficulty_breakdown": {"1_쉬움": 20, "2_보통": 16, "3_어려움": 9},
        "chapter_breakdown": {"1장": 8, "2장": 7, "3장": 8, "4장": 7, "5장": 8, "6장": 7},
        "answer_no_distribution": {1: 9, 2: 9, 3: 9, 4: 9, 5: 9},
        "groundedness": {"확인": 40, "미확인": 5},
        "targets_vs_actual": {"difficulty": {"easy": {"target": 0.45, "actual": 0.44}}},
    }
    base.update(overrides)
    return base


# ===========================================================================
# T004: ExamenBlueprint
# ===========================================================================


class TestExamenBlueprint:
    def test_positive_valid(self) -> None:
        """Valid blueprint with total_items=45 and balanced source_mix."""
        ExamenBlueprint(**_base_blueprint())

    def test_positive_boundary_40(self) -> None:
        """total_items=40 is the lower boundary (inclusive)."""
        ExamenBlueprint(
            **_base_blueprint(
                total_items=40,
                source_mix={"formative": 10, "quiz": 15, "textbook": 15},
            )
        )

    def test_positive_boundary_50(self) -> None:
        """total_items=50 is the upper boundary (inclusive)."""
        ExamenBlueprint(
            **_base_blueprint(
                total_items=50,
                source_mix={"formative": 10, "quiz": 15, "textbook": 25},
            )
        )

    def test_negative_total_items_too_low(self) -> None:
        """total_items=39 is below the minimum of 40 → ValidationError."""
        with pytest.raises(ValidationError):
            ExamenBlueprint(
                **_base_blueprint(
                    total_items=39,
                    source_mix={"formative": 9, "quiz": 15, "textbook": 15},
                )
            )

    def test_negative_total_items_too_high(self) -> None:
        """total_items=51 is above the maximum of 50 → ValidationError."""
        with pytest.raises(ValidationError):
            ExamenBlueprint(
                **_base_blueprint(
                    total_items=51,
                    source_mix={"formative": 11, "quiz": 15, "textbook": 25},
                )
            )

    def test_negative_source_mix_sum_mismatch(self) -> None:
        """sum(source_mix) != total_items → ValidationError."""
        with pytest.raises(ValidationError):
            ExamenBlueprint(
                **_base_blueprint(
                    total_items=45,
                    source_mix={"formative": 10, "quiz": 15, "textbook": 19},  # sum=44
                )
            )

    def test_negative_difficulty_targets_sum_mismatch(self) -> None:
        """difficulty_targets sum != 1.0 → ValidationError."""
        with pytest.raises(ValidationError):
            ExamenBlueprint(
                **_base_blueprint(
                    difficulty_targets={"easy": 0.50, "medium": 0.35, "hard": 0.20},
                )
            )

    def test_negative_extra_field(self) -> None:
        """extra='forbid' rejects unknown fields."""
        with pytest.raises(ValidationError):
            ExamenBlueprint(**_base_blueprint(unknown_field="oops"))

    def test_positive_difficulty_targets_within_epsilon(self) -> None:
        """Difficulty targets summing to 1.0 within ±1e-6 must pass."""
        # 0.45 + 5e-7 + 0.35 + (0.20 - 5e-7) = 1.0 within tolerance
        ExamenBlueprint(
            **_base_blueprint(
                difficulty_targets={
                    "easy": 0.45 + 5e-7,
                    "medium": 0.35,
                    "hard": 0.20 - 5e-7,
                },
            )
        )

    def test_negative_difficulty_targets_outside_epsilon(self) -> None:
        """Difficulty targets summing to 1.0 + 2e-6 (outside ±1e-6) → ValidationError."""
        with pytest.raises(ValidationError):
            ExamenBlueprint(
                **_base_blueprint(
                    difficulty_targets={
                        "easy": 0.45 + 2e-6,
                        "medium": 0.35,
                        "hard": 0.20,
                    },
                )
            )


# ===========================================================================
# T005: CurriculumMap + CurriculumEntry
# ===========================================================================


class TestCurriculumMap:
    def test_positive_valid(self) -> None:
        """Valid CurriculumMap with one entry."""
        CurriculumMap(**_base_curriculum_map())

    def test_positive_multi_week_same_chapter(self) -> None:
        """Same chapter_no across multiple weeks is allowed (e.g., ch9 = weeks 10+11)."""
        entries = [
            CurriculumEntry(week=10, chapter="9장 근육계", chapter_no=9, sections=["수축"]),
            CurriculumEntry(week=11, chapter="9장 근육계", chapter_no=9, sections=["이완"]),
        ]
        CurriculumMap(semester=_SEM, course_slug=_COURSE, entries=entries)

    def test_positive_entry_no_subtopic(self) -> None:
        """subtopic=None is valid (optional field)."""
        CurriculumEntry(**_base_entry(subtopic=None))

    def test_negative_extra_field_map(self) -> None:
        """extra='forbid' on CurriculumMap."""
        with pytest.raises(ValidationError):
            CurriculumMap(**_base_curriculum_map(spurious="x"))

    def test_negative_extra_field_entry(self) -> None:
        """extra='forbid' on CurriculumEntry."""
        with pytest.raises(ValidationError):
            CurriculumEntry(**_base_entry(unknown="x"))


# ===========================================================================
# T006: SourceInventoryEntry
# ===========================================================================


class TestSourceInventoryEntry:
    def test_positive_formative(self) -> None:
        """Valid formative source entry."""
        SourceInventoryEntry(**_base_source_inventory())

    def test_positive_quiz(self) -> None:
        """Valid quiz source entry."""
        SourceInventoryEntry(
            **_base_source_inventory(
                source="quiz",
                source_ref="퀴즈:1주#3",
                model_answer=None,
                keywords=[],
                rubric=None,
                options=["보기1", "보기2", "보기3", "보기4", "보기5"],
                answer="1",
            )
        )

    def test_positive_empty_keywords_default(self) -> None:
        """keywords defaults to empty list — omitting it works."""
        SourceInventoryEntry(
            semester=_SEM,
            course_slug=_COURSE,
            source="formative",
            source_ref="형성평가:1장#2",
            stem="다음을 설명하시오.",
        )

    def test_negative_invalid_source(self) -> None:
        """source must be one of 'formative' or 'quiz'."""
        with pytest.raises(ValidationError):
            SourceInventoryEntry(**_base_source_inventory(source="textbook"))

    def test_negative_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            SourceInventoryEntry(**_base_source_inventory(extra_col="x"))


# ===========================================================================
# T007: TextbookChunk
# ===========================================================================


class TestTextbookChunk:
    def test_positive_valid(self) -> None:
        TextbookChunk(**_base_textbook_chunk())

    def test_positive_no_section(self) -> None:
        """section is optional."""
        TextbookChunk(**_base_textbook_chunk(section=None))

    def test_positive_empty_removed_spans_default(self) -> None:
        """removed_spans defaults to []."""
        data = {k: v for k, v in _base_textbook_chunk().items() if k != "removed_spans"}
        TextbookChunk(**data)

    def test_positive_single_line(self) -> None:
        """line_end == line_start is valid (single-line chunk)."""
        TextbookChunk(**_base_textbook_chunk(line_start=10, line_end=10))

    def test_negative_line_end_before_start(self) -> None:
        """line_end < line_start → ValidationError (V1)."""
        with pytest.raises(ValidationError):
            TextbookChunk(**_base_textbook_chunk(line_start=25, line_end=10))

    def test_negative_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            TextbookChunk(**_base_textbook_chunk(junk="x"))


# ===========================================================================
# T008: EmphasisCell
# ===========================================================================


class TestEmphasisCell:
    def test_positive_emphasized(self) -> None:
        """All classes emphasized → is_emphasized=True is consistent."""
        EmphasisCell(**_base_emphasis_cell())

    def test_positive_not_emphasized(self) -> None:
        """Only some classes emphasized → is_emphasized=False."""
        EmphasisCell(
            **_base_emphasis_cell(
                emphasized_class_count=2,
                available_class_count=3,
                is_emphasized=False,
            )
        )

    def test_positive_available_zero_not_emphasized(self) -> None:
        """available_class_count=0 → is_emphasized must be False."""
        EmphasisCell(
            **_base_emphasis_cell(
                emphasized_class_count=0,
                available_class_count=0,
                is_emphasized=False,
            )
        )

    def test_negative_is_emphasized_inconsistent(self) -> None:
        """is_emphasized=True when available=0 → ValidationError (inconsistent)."""
        with pytest.raises(ValidationError):
            EmphasisCell(
                **_base_emphasis_cell(
                    emphasized_class_count=0,
                    available_class_count=0,
                    is_emphasized=True,
                )
            )

    def test_negative_is_emphasized_false_when_should_be_true(self) -> None:
        """emphasized==available and available>0 but is_emphasized=False → ValidationError."""
        with pytest.raises(ValidationError):
            EmphasisCell(
                **_base_emphasis_cell(
                    emphasized_class_count=3,
                    available_class_count=3,
                    is_emphasized=False,
                )
            )

    def test_negative_emphasized_exceeds_available(self) -> None:
        """emphasized_class_count > available_class_count → ValidationError."""
        with pytest.raises(ValidationError):
            EmphasisCell(
                **_base_emphasis_cell(
                    emphasized_class_count=4,
                    available_class_count=3,
                    is_emphasized=True,
                )
            )

    def test_negative_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            EmphasisCell(**_base_emphasis_cell(bad="x"))


# ===========================================================================
# T009: ExamItemDraft + TextbookEvidence
# ===========================================================================


class TestTextbookEvidence:
    def test_positive_confirmed(self) -> None:
        TextbookEvidence(**_base_textbook_evidence())

    def test_positive_unconfirmed_minimal(self) -> None:
        TextbookEvidence(source_file="ch01.txt", status="미확인")

    def test_negative_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            TextbookEvidence(**_base_textbook_evidence(status="pending"))

    def test_negative_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            TextbookEvidence(**_base_textbook_evidence(extra="x"))


class TestExamItemDraft:
    def test_positive_valid(self) -> None:
        """Fully valid ExamItemDraft constructs without error."""
        ExamItemDraft(**_base_exam_item_draft())

    def test_positive_no_evidence(self) -> None:
        """textbook_evidence=None is allowed."""
        ExamItemDraft(**_base_exam_item_draft(textbook_evidence=None))

    def test_positive_formative_source(self) -> None:
        """source='formative' with source_ref provided."""
        ExamItemDraft(**_base_exam_item_draft(source="formative", source_ref="형성평가:1장#1"))

    def test_negative_options_len_not_5(self) -> None:
        """len(options) != 5 → ValidationError."""
        with pytest.raises(ValidationError):
            ExamItemDraft(**_base_exam_item_draft(options=["a", "b", "c", "d"]))

    def test_negative_options_len_6(self) -> None:
        """len(options) == 6 → ValidationError."""
        with pytest.raises(ValidationError):
            ExamItemDraft(**_base_exam_item_draft(options=["a", "b", "c", "d", "e", "f"]))

    def test_negative_answer_no_zero(self) -> None:
        """answer_no=0 < 1 → ValidationError."""
        with pytest.raises(ValidationError):
            ExamItemDraft(**_base_exam_item_draft(answer_no=0))

    def test_negative_answer_no_six(self) -> None:
        """answer_no=6 > 5 → ValidationError."""
        with pytest.raises(ValidationError):
            ExamItemDraft(**_base_exam_item_draft(answer_no=6))

    def test_negative_distractor_rationale_len_not_5(self) -> None:
        """len(distractor_rationale) != 5 → ValidationError."""
        with pytest.raises(ValidationError):
            ExamItemDraft(**_base_exam_item_draft(distractor_rationale=["a", "b", "c"]))

    def test_negative_invalid_difficulty(self) -> None:
        """difficulty must be one of the three literal values."""
        with pytest.raises(ValidationError):
            ExamItemDraft(**_base_exam_item_draft(difficulty="easy"))

    def test_negative_invalid_adoption_status(self) -> None:
        """adoption_status must be one of the four literal values."""
        with pytest.raises(ValidationError):
            ExamItemDraft(**_base_exam_item_draft(adoption_status="draft"))

    def test_negative_item_no_zero(self) -> None:
        """item_no=0 → ValidationError (ge=1)."""
        with pytest.raises(ValidationError):
            ExamItemDraft(**_base_exam_item_draft(item_no=0))

    def test_negative_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            ExamItemDraft(**_base_exam_item_draft(unknown="x"))


# ===========================================================================
# T010: ExamenManifest
# ===========================================================================


class TestExamenManifest:
    def test_positive_valid(self) -> None:
        ExamenManifest(**_base_examen_manifest())

    def test_positive_dry_run_backend(self) -> None:
        """none(dry-run) is a valid llm_backend value."""
        ExamenManifest(**_base_examen_manifest(llm_backend="none(dry-run)", llm_model=None))

    def test_positive_no_cache_hit_rate(self) -> None:
        """cache_hit_rate=None is valid."""
        ExamenManifest(**_base_examen_manifest(cache_hit_rate=None))

    def test_negative_invalid_llm_backend(self) -> None:
        """llm_backend must be one of the three literal values."""
        with pytest.raises(ValidationError):
            ExamenManifest(**_base_examen_manifest(llm_backend="local"))

    def test_negative_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            ExamenManifest(**_base_examen_manifest(oops="x"))


# ===========================================================================
# T011: __init__.py exports
# ===========================================================================


class TestExamenSchemaExports:
    """Verify all 7 new schemas are importable from paideia_shared.schemas."""

    def test_examen_blueprint_exported(self) -> None:
        from paideia_shared.schemas import ExamenBlueprint as _  # noqa: F401

    def test_curriculum_map_exported(self) -> None:
        from paideia_shared.schemas import CurriculumMap as _  # noqa: F401

    def test_curriculum_entry_exported(self) -> None:
        from paideia_shared.schemas import CurriculumEntry as _  # noqa: F401

    def test_source_inventory_entry_exported(self) -> None:
        from paideia_shared.schemas import SourceInventoryEntry as _  # noqa: F401

    def test_textbook_chunk_exported(self) -> None:
        from paideia_shared.schemas import TextbookChunk as _  # noqa: F401

    def test_emphasis_cell_exported(self) -> None:
        from paideia_shared.schemas import EmphasisCell as _  # noqa: F401

    def test_exam_item_draft_exported(self) -> None:
        from paideia_shared.schemas import ExamItemDraft as _  # noqa: F401

    def test_textbook_evidence_exported(self) -> None:
        from paideia_shared.schemas import TextbookEvidence as _  # noqa: F401

    def test_examen_manifest_exported(self) -> None:
        from paideia_shared.schemas import ExamenManifest as _  # noqa: F401
