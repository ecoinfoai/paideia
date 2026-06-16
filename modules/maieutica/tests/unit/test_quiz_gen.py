"""T027 (RED) — unit tests for ``maieutica.generate.quiz_gen.generate_quiz_item``.

A FAKE backend returns a canned valid JSON response; ``generate_quiz_item``
parses it into a COMPLETE, schema-valid ``QuizItemCandidate`` per the
staged-enrichment contract (provisional difficulty "중", textbook_evidence None,
leap text present, combined explanation folded, soft length flags computed,
question_type LLM-emitted + enum-validated with deterministic fallback).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from maieutica.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    InputHashCache,
    LLMBackend,
)
from maieutica.plan.slots import Slot, plan_slots
from paideia_shared.schemas import (
    MaieuticaGenerationSpec,
    QuizItemCandidate,
    TextbookChunk,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SHORT_OPTION = "② 기관지는 공기 통로이다."  # 15 chars (below the 30-char floor)

_CANNED_QUIZ_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "중",
    "stem_polarity": "부정형",
    "text": "다음 중 허파꽈리에 대한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① 허파꽈리는 가스교환이 일어나는 호흡계통의 기본 단위이다.",
        "② 허파꽈리 벽은 단층편평상피로 구성되어 매우 얇은 편이다.",
        "③ 허파꽈리 주위에는 모세혈관이 그물처럼 분포하고 있다.",
        "④ 허파꽈리에서는 산소와 이산화탄소가 확산으로 교환된다.",
        "⑤ 허파꽈리는 기관 안에서 직접 공기를 데우는 기능을 한다.",
    ],
    "answer_no": 5,
    "option_evidence": [
        "교재: 허파꽈리는 가스교환의 기본 단위.",
        "교재: 허파꽈리 벽은 단층편평상피.",
        "교재: 모세혈관이 그물처럼 분포.",
        "교재: 산소·이산화탄소 확산 교환.",
        "틀린 진술: 기관이 공기를 데움.",
    ],
    "wrong_explanation": (
        "허파꽈리는 공기를 데우는 기관이 아니라 가스교환의 장소이다. "
        "공기를 데우고 거르는 것은 코안과 기관의 기능이다. "
        "허파꽈리의 핵심은 얇은 벽을 통한 산소와 이산화탄소의 확산 교환이다."
    ),
    "leap_explanation": (
        "정답을 맞혔다면 허파꽈리의 기능을 이해한 것이다. "
        "나아가 호흡막의 두께가 확산 효율에 미치는 영향, "
        "그리고 폐기종에서 허파꽈리 벽 손상이 가스교환을 어떻게 저하시키는지 연결해 보라."
    ),
    "intent": "허파꽈리의 기능을 정확히 이해하는지 확인한다.",
    "key_concept": "허파꽈리",
    "section": "1. 허파꽈리와 가스교환",
}


class FakeBackend(LLMBackend):
    """Returns a canned structured JSON; counts calls."""

    def __init__(self, raw: dict[str, Any] | str | None = None) -> None:
        self._raw = raw if raw is not None else _CANNED_QUIZ_JSON
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        raw_text = (
            self._raw if isinstance(self._raw, str) else json.dumps(self._raw, ensure_ascii=False)
        )
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=raw_text,
            model="fake-model",
            cache_hit=False,
        )


def _make_spec(
    *, week: int = 9, chapter_no: int = 8, chapter: str = "8장 호흡계통"
) -> MaieuticaGenerationSpec:
    return MaieuticaGenerationSpec(
        semester="2026-1",
        course_slug="anatomy",
        week=week,
        chapter_no=chapter_no,
        chapter=chapter,
        quiz_count=20,
        formative_count=3,
    )


def _make_chunks(chapter_no: int = 8, chapter: str = "8장 호흡계통") -> list[TextbookChunk]:
    return [
        TextbookChunk(
            semester="2026-1",
            course_slug="anatomy",
            chunk_id=f"chunk{chapter_no:02d}00",
            chapter_no=chapter_no,
            chapter=chapter,
            section="1. 허파꽈리와 가스교환",
            source_file=f"{chapter_no}장.txt",
            line_start=1,
            line_end=20,
            text="허파꽈리에서 산소와 이산화탄소가 확산으로 교환된다.",
            removed_spans=[],
        )
    ]


def _first_quiz_slot(spec: MaieuticaGenerationSpec) -> Slot:
    return next(s for s in plan_slots(spec) if s.kind == "quiz")


def _generate(
    *,
    raw: dict[str, Any] | str | None = None,
    spec: MaieuticaGenerationSpec | None = None,
    slot: Slot | None = None,
    chunks: list[TextbookChunk] | None = None,
    cache_dir: Path,
) -> QuizItemCandidate:
    from maieutica.generate.quiz_gen import generate_quiz_item

    if spec is None:
        spec = _make_spec()
    if slot is None:
        slot = _first_quiz_slot(spec)
    if chunks is None:
        chunks = _make_chunks(chapter_no=spec.chapter_no)
    backend = FakeBackend(raw=raw)
    cache = InputHashCache(backend=backend, cache_dir=cache_dir)
    return generate_quiz_item(slot, spec, chunks, cache)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateQuizItem:
    def test_returns_quiz_item_candidate(self, tmp_path: Path) -> None:
        item = _generate(cache_dir=tmp_path / "c")
        assert isinstance(item, QuizItemCandidate)

    def test_five_options(self, tmp_path: Path) -> None:
        item = _generate(cache_dir=tmp_path / "c")
        assert len(item.options) == 5

    def test_option_evidence_len_5(self, tmp_path: Path) -> None:
        item = _generate(cache_dir=tmp_path / "c")
        assert len(item.option_evidence) == 5

    def test_answer_no_in_range(self, tmp_path: Path) -> None:
        item = _generate(cache_dir=tmp_path / "c")
        assert 1 <= item.answer_no <= 5

    def test_leap_text_present(self, tmp_path: Path) -> None:
        item = _generate(cache_dir=tmp_path / "c")
        assert item.leap.text
        # leap groundedness is filled later (T037/T038)
        assert item.leap.textbook_evidence is None

    def test_answer_explanation_combined_is_fold(self, tmp_path: Path) -> None:
        item = _generate(cache_dir=tmp_path / "c")
        expected = f"{item.wrong_explanation} ─ 도약 ─ {item.leap.text}"
        assert item.answer_explanation_combined == expected

    def test_provisional_difficulty(self, tmp_path: Path) -> None:
        """difficulty is provisional '중' (finalized by T030)."""
        item = _generate(cache_dir=tmp_path / "c")
        assert item.difficulty == "중"

    def test_textbook_evidence_none(self, tmp_path: Path) -> None:
        """textbook_evidence is None (filled by verify/groundedness T028)."""
        item = _generate(cache_dir=tmp_path / "c")
        assert item.textbook_evidence is None

    def test_question_type_in_literal(self, tmp_path: Path) -> None:
        item = _generate(cache_dir=tmp_path / "c")
        assert item.question_type in ("지식축적", "맥락통찰")

    def test_question_type_emitted_value_preserved(self, tmp_path: Path) -> None:
        raw = dict(_CANNED_QUIZ_JSON)
        raw["question_type"] = "맥락통찰"
        item = _generate(raw=raw, cache_dir=tmp_path / "c")
        assert item.question_type == "맥락통찰"

    def test_question_type_invalid_falls_back(self, tmp_path: Path) -> None:
        """Bad question_type → deterministic fallback, not a crash."""
        raw = dict(_CANNED_QUIZ_JSON)
        raw["question_type"] = "엉터리유형"
        item = _generate(raw=raw, cache_dir=tmp_path / "c")
        assert item.question_type == "지식축적"

    def test_question_type_missing_falls_back(self, tmp_path: Path) -> None:
        raw = dict(_CANNED_QUIZ_JSON)
        del raw["question_type"]
        item = _generate(raw=raw, cache_dir=tmp_path / "c")
        assert item.question_type == "지식축적"

    def test_option_length_ok_true_for_good_options(self, tmp_path: Path) -> None:
        item = _generate(cache_dir=tmp_path / "c")
        assert item.option_length_ok is True

    def test_option_length_ok_false_for_short_option(self, tmp_path: Path) -> None:
        raw = dict(_CANNED_QUIZ_JSON)
        opts = list(raw["options"])
        opts[1] = _SHORT_OPTION  # 15 chars — below the 30-char floor
        raw["options"] = opts
        item = _generate(raw=raw, cache_dir=tmp_path / "c")
        assert item.option_length_ok is False

    def test_explanation_length_ok_true_for_canned(self, tmp_path: Path) -> None:
        """Canned wrong + leap are each <=200 chars → flag is True."""
        item = _generate(cache_dir=tmp_path / "c")
        assert item.explanation_length_ok is True

    def test_option_evidence_padded_with_sentinel(self, tmp_path: Path) -> None:
        """Fewer than 5 evidence entries → padded to 5 with the sentinel."""
        from maieutica.generate.quiz_gen import MISSING_EVIDENCE_PLACEHOLDER

        raw = dict(_CANNED_QUIZ_JSON)
        raw["option_evidence"] = ["교재: 근거1", "교재: 근거2"]  # only 2 of 5
        item = _generate(raw=raw, cache_dir=tmp_path / "c")
        assert len(item.option_evidence) == 5
        assert item.option_evidence[:2] == ["교재: 근거1", "교재: 근거2"]
        assert item.option_evidence[2:] == [MISSING_EVIDENCE_PLACEHOLDER] * 3

    def test_identity_fields_from_slot_and_spec(self, tmp_path: Path) -> None:
        spec = _make_spec(week=9, chapter_no=8, chapter="8장 호흡계통")
        item = _generate(spec=spec, cache_dir=tmp_path / "c")
        assert item.semester == "2026-1"
        assert item.course_slug == "anatomy"
        assert item.week == 9
        assert item.chapter_no == 8
        assert item.chapter == "8장 호흡계통"
        assert item.item_no >= 1

    def test_default_status_fields(self, tmp_path: Path) -> None:
        item = _generate(cache_dir=tmp_path / "c")
        assert item.adoption_status == "생성"
        assert item.duplicate_flag is False
        assert item.review_note == ""
        assert item.note is None

    def test_malformed_json_raises_clear_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="JSON"):
            _generate(raw="this is not json {", cache_dir=tmp_path / "c")

    def test_cache_rerun_byte_identical(self, tmp_path: Path) -> None:
        spec = _make_spec()
        slot = _first_quiz_slot(spec)
        chunks = _make_chunks(chapter_no=8)
        backend = FakeBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path / "c")
        from maieutica.generate.quiz_gen import generate_quiz_item

        a = generate_quiz_item(slot, spec, chunks, cache)
        b = generate_quiz_item(slot, spec, chunks, cache)
        assert a.model_dump() == b.model_dump()
        assert backend.call_count == 1
