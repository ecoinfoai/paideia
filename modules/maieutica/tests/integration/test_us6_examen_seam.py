"""T058 — Integration test: examen input-seam identifiers (US6, SC-013/FR-024).

Build → open ``출제후보_완전판.yaml`` and assert every quiz candidate carries
the examen input-seam identifiers required for downstream consumption:

- ``week``: present and matches the spec week.
- ``chapter_no``: present and matches the spec chapter_no.
- ``chapter``: present and matches the spec chapter display name.
- Source identifier: ``textbook_evidence.source_file`` (when evidence exists)
  or ``chunk_ids`` in the bundle metadata (seam-level traceability).
- ``question_type`` ∈ ``{"지식축적", "맥락통찰"}`` — matching
  ``examen.schemas.ExamItemDraft.question_type`` Literal values exactly.
- ``difficulty`` ∈ ``{"상", "중", "하"}`` (advisory — examen re-derives its own
  ``"1_쉬움"/"2_보통"/"3_어려움"`` scale from its blueprint; the maieutica value
  is advisory only and is NOT converted by the examen seam).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from maieutica.ingest.spec_load import load_curriculum_map, load_generation_spec
from maieutica.plan.slots import plan_slots
from paideia_shared.schemas import MaieuticaGenerationSpec

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_QUIZ_COUNT = 3
_FORMATIVE_COUNT = 1

_KEY_CONCEPTS = ["폐포", "기관지", "가로막"]
_FORMATIVE_TOPICS = ["가스교환"]

# Verbatim subsection body line per key_concept — the answer-anchored,
# subsection-scoped groundedness check (US1) confirms an item only when the
# CORRECT option's evidence is a verbatim line of its assigned subsection.  These
# distinct lines yield 확인 with distinct anchors (no dedup, no 미확인 exclusion).
_CONCEPT_EVIDENCE = {
    "폐포": "폐포는 가스 교환이 일어나는 포상 구조이다.",
    "기관지": "기관지는 공기를 폐로 전달하는 통로이다.",
    "가로막": "가로막은 수축하여 흉강 부피를 늘린다.",
}

# Chapter body must contain each key_concept for evidence=확인 to fire;
# the seam test also checks source_file traceability regardless of status.
_CHAPTER_TXT = "\n".join(
    [
        "8장 호흡계통",
        "",
        "1. 호흡계통의 구조",
        "코는 후각과 공기 가습을 담당한다.",
        "폐포는 가스 교환이 일어나는 포상 구조이다.",
        "기관지는 공기를 폐로 전달하는 통로이다.",
        "가로막은 수축하여 흉강 부피를 늘린다.",
        "허파꽈리에서 가스교환이 분압 차이로 일어난다.",
        "",
    ]
)

# Allowed values (matches examen ExamItemDraft.question_type Literal)
_VALID_QUESTION_TYPES = {"지식축적", "맥락통찰"}
# Allowed difficulty values (advisory; examen re-derives its own scale)
_VALID_DIFFICULTIES = {"상", "중", "하"}


def _quiz_item_json(item_no: int, key_concept: str, answer_no: int) -> dict:
    options = [
        f"{marker} {key_concept} 관련 보기 {item_no}-{i} 충분한 길이를 가진 보기입니다 abcde"
        for i, marker in enumerate("①②③④⑤", start=1)
    ]
    return {
        "question_type": "지식축적",
        "stem_polarity": "부정형",
        "text": f"{item_no}번 문제: {key_concept}에 대해 옳지 않은 것은?",
        "options": options,
        "answer_no": answer_no,
        # Correct option's evidence = verbatim subsection line → status="확인".
        "option_evidence": [
            _CONCEPT_EVIDENCE[key_concept] if i == answer_no else f"{key_concept} 근거 {i}"
            for i in range(1, 6)
        ],
        "wrong_explanation": f"{key_concept} 관련 오답 설명입니다.",
        "leap_explanation": f"{key_concept} 다음 개념으로의 도약 설명입니다.",
        "key_concept": key_concept,
        "section": "1. 호흡계통의 구조",
    }


def _formative_item_json(no: int, topic: str) -> dict:
    return {
        "no": no,
        "chapter_no": _CHAPTER_NO,
        "topic": topic,
        "question": f"{no}번 형성문항: {topic} 원리를 200자 내외로 서술하시오.",
        "limit": "200자 내외",
        "model_answer": f"{topic}는 교재에 따르면 핵심 과정이다.",
        "purpose": f"{topic} 이해 여부 확인.",
        "keywords": [topic, "분압", "확산"],
        "rubric_high": f"{topic} 핵심 개념 전부 + 정확한 용어.",
        "rubric_mid": f"{topic} 일부 포함, 용어 부정확.",
        "rubric_low": f"{topic} 핵심 누락.",
        "support_high": f"{topic}를 다음 심화 개념으로 잇는 도약 활동 안내.",
        "support_mid": f"{topic} 관련 교재 그림으로 복습 지도.",
        "support_low": f"{topic} 기본 개념부터 재학습 경로 안내.",
    }


def _spec() -> MaieuticaGenerationSpec:
    return MaieuticaGenerationSpec.model_validate(
        {
            "semester": _SEMESTER,
            "course_slug": _COURSE,
            "week": _WEEK,
            "chapter_no": _CHAPTER_NO,
            "chapter": _CHAPTER,
            "quiz_count": _QUIZ_COUNT,
            "formative_count": _FORMATIVE_COUNT,
        }
    )


def _build_bronze(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    bronze.mkdir(parents=True, exist_ok=True)

    (bronze / f"{_CHAPTER} 호흡.txt").write_text(_CHAPTER_TXT, encoding="utf-8")

    spec = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "week": _WEEK,
        "chapter_no": _CHAPTER_NO,
        "chapter": _CHAPTER,
        "quiz_count": _QUIZ_COUNT,
        "formative_count": _FORMATIVE_COUNT,
    }
    (bronze / "generation_spec.yaml").write_text(
        json.dumps(spec, ensure_ascii=False), encoding="utf-8"
    )

    curriculum = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": _WEEK,
                "chapter": _CHAPTER,
                "chapter_no": _CHAPTER_NO,
                "sections": ["1. 호흡계통의 구조"],
            }
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        json.dumps(curriculum, ensure_ascii=False), encoding="utf-8"
    )
    return bronze, data_root


def _write_canned_responses(responses_dir: Path) -> None:
    responses_dir.mkdir(parents=True, exist_ok=True)
    slots = plan_slots(_spec())

    quiz_slots = [s for s in slots if s.kind == "quiz"]
    for idx, slot in enumerate(quiz_slots):
        key_concept = _KEY_CONCEPTS[idx % len(_KEY_CONCEPTS)]
        item_json = _quiz_item_json(slot.ordinal, key_concept, (idx % 5) + 1)
        _write_envelope(responses_dir, slot.slot_id, item_json)

    formative_slots = [s for s in slots if s.kind == "formative"]
    for idx, slot in enumerate(formative_slots):
        topic = _FORMATIVE_TOPICS[idx % len(_FORMATIVE_TOPICS)]
        item_json = _formative_item_json(slot.ordinal, topic)
        _write_envelope(responses_dir, slot.slot_id, item_json)


def _write_envelope(responses_dir: Path, slot_id: str, item_json: dict) -> None:
    envelope = {
        "slot_id": slot_id,
        "raw_text": json.dumps(item_json, ensure_ascii=False),
        "model": "canned-subscription",
    }
    (responses_dir / f"{slot_id}.json").write_text(
        json.dumps(envelope, ensure_ascii=False), encoding="utf-8"
    )


def test_us6_examen_seam_identifiers(tmp_path: Path) -> None:
    """Build → yaml: every quiz candidate carries the examen input-seam identifiers.

    SC-013 / FR-024: verifies the no-conversion seam contract between maieutica
    and examen.  Specifically:

    - ``week``, ``chapter_no``, ``chapter`` present and correct.
    - Source traceability: ``textbook_evidence.source_file`` is populated when
      evidence status is '확인'; for '미확인', the candidate still carries
      ``chapter_no`` for chapter-level traceability.
    - ``question_type`` ∈ ``{"지식축적", "맥락통찰"}`` — exact match with
      ``examen.schemas.ExamItemDraft.question_type`` Literal values.
    - ``difficulty`` ∈ ``{"상", "중", "하"}`` (advisory only).

    NOTE on difficulty advisory status: examen re-derives difficulty as
    ``"1_쉬움" / "2_보통" / "3_어려움"`` from its own blueprint weighting.
    Maieutica's ``"상"/"중"/"하"`` is purely advisory and is NOT part of the
    no-conversion seam — examen does not consume it for its own difficulty field.
    """
    from maieutica.generate.backend import SubscriptionBackend
    from maieutica.pipeline import build

    bronze, data_root = _build_bronze(tmp_path)
    spec = load_generation_spec(bronze / "generation_spec.yaml")
    curriculum_map = load_curriculum_map(bronze / "curriculum_map.yaml")

    silver = data_root / "silver" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    staging_dir = silver / "staging"
    responses_dir = silver / "responses"
    _write_canned_responses(responses_dir)

    backend = SubscriptionBackend(staging_dir=staging_dir, responses_dir=responses_dir)

    _, run_dir = build(
        spec=spec,
        curriculum_map=curriculum_map,
        bronze_dir=bronze,
        data_root=data_root,
        backend=backend,
        generation_spec_path=bronze / "generation_spec.yaml",
        curriculum_map_path=bronze / "curriculum_map.yaml",
    )

    yaml_path = run_dir / "출제후보_완전판.yaml"
    assert yaml_path.is_file(), f"expected yaml at {yaml_path}"
    doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    quiz_items = doc["quiz"]
    assert len(quiz_items) == _QUIZ_COUNT

    for i, q in enumerate(quiz_items):
        label = f"quiz[{i}] (item_no={q.get('item_no')})"

        # --- examen seam identifiers ---
        assert q.get("week") == _WEEK, f"{label}: week mismatch"
        assert q.get("chapter_no") == _CHAPTER_NO, f"{label}: chapter_no mismatch"
        assert q.get("chapter") == _CHAPTER, f"{label}: chapter mismatch"

        # --- question_type matches examen ExamItemDraft Literal ---
        qt = q.get("question_type")
        assert qt in _VALID_QUESTION_TYPES, (
            f"{label}: question_type {qt!r} not in {_VALID_QUESTION_TYPES}"
        )

        # --- difficulty (advisory) within the maieutica scale ---
        diff = q.get("difficulty")
        assert diff in _VALID_DIFFICULTIES, (
            f"{label}: difficulty {diff!r} not in {_VALID_DIFFICULTIES}\n"
            "NOTE: maieutica 'difficulty' is advisory; examen re-derives "
            "'1_쉬움'/'2_보통'/'3_어려움' from its own blueprint — these scales "
            "are intentionally separate and must NOT be unified (spec 009 §5)."
        )

        # --- source traceability: textbook_evidence present ---
        te = q.get("textbook_evidence")
        assert te is not None, (
            f"{label}: textbook_evidence is None — source traceability missing"
        )
        # source_file is always required (even when status is '미확인')
        assert te.get("source_file"), (
            f"{label}: textbook_evidence.source_file is empty"
        )
        # status must be a known value
        assert te.get("status") in {"확인", "미확인"}, (
            f"{label}: textbook_evidence.status {te.get('status')!r} invalid"
        )

    # Confirm all I/O is under tmp_path (no real data/ touched).
    assert str(run_dir).startswith(str(tmp_path))
