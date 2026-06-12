"""T025 — Integration test: full quiz build pipeline (US1).

Exercises ``maieutica.pipeline.build`` end-to-end on a small fixture chapter,
generation_spec, and curriculum_map, with a ``SubscriptionBackend`` fed by
canned per-slot response files (no network, no real ``data/``):

1. Build a temp Bronze tree with a chapter ``.txt`` whose body contains the
   canned items' ``key_concept`` strings (so groundedness resolves to 확인).
2. Pre-fill ``responses/{slot_id}.json`` for every quiz slot (envelope
   ``{slot_id, raw_text, model}`` where ``raw_text`` is the quiz item JSON).
3. Call ``build(...)`` with a ``SubscriptionBackend``.

Assertions (SC-003 / SC-007 / atomicity):
- ``QuestionUploadExcel_{week}주차.xls`` exists with ``quiz_count`` data rows.
- Each item: 5 options, exactly 1 answer (answer_no in 1..5), options 30–50 chars.
- Every item's ``textbook_evidence.status`` is explicitly 확인 or 미확인 (SC-007),
  and the fixture is arranged so the canned key_concepts anchor to 확인.
- ``manifest_maieutica.json`` is present and well-formed.
- No real ``data/`` directory is touched (everything under ``tmp_path``).
"""

from __future__ import annotations

import json
from pathlib import Path

import xlrd
from maieutica.ingest.spec_load import load_curriculum_map, load_generation_spec
from maieutica.plan.slots import plan_slots
from paideia_shared.schemas import MaieuticaGenerationSpec

# ---------------------------------------------------------------------------
# Fixture content
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_QUIZ_COUNT = 3
_FORMATIVE_COUNT = 1

# Each canned item's key_concept MUST appear verbatim in the chapter body below
# so that verify_groundedness resolves it to status="확인" (SC-007).
_KEY_CONCEPTS = ["폐포", "기관지", "가로막"]

# A small chapter .txt: a numbered section heading plus body lines that mention
# each key concept.  The cleaner keeps body text and numbered headings.
_CHAPTER_TXT = "\n".join(
    [
        "8장 호흡계통",
        "",
        "1. 호흡계통의 구조",
        "코는 후각과 공기 가습을 담당한다.",
        "폐포는 가스 교환이 일어나는 포상 구조이다.",
        "기관지는 공기를 폐로 전달하는 통로이다.",
        "가로막은 수축하여 흉강 부피를 늘린다.",
        "",
    ]
)


def _quiz_item_json(item_no: int, key_concept: str, answer_no: int) -> dict:
    """Build a schema-valid quiz item JSON for the canned LLM response.

    Options are padded to land inside the 30–50 codepoint window.
    """
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
        "option_evidence": [f"{key_concept} 근거 {i}" for i in range(1, 6)],
        "wrong_explanation": f"{key_concept} 관련 오답 설명입니다.",
        "leap_explanation": f"{key_concept} 다음 개념으로의 도약 설명입니다.",
        "key_concept": key_concept,
        "section": "1. 호흡계통의 구조",
    }


def _build_bronze(tmp_path: Path) -> tuple[Path, Path]:
    """Lay out the Bronze tree and return ``(bronze_dir, data_root)``."""
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
    """Write ``responses/{slot_id}.json`` for every quiz slot."""
    responses_dir.mkdir(parents=True, exist_ok=True)
    spec = MaieuticaGenerationSpec.model_validate(
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
    slots = plan_slots(spec)
    quiz_slots = [s for s in slots if s.kind == "quiz"]
    for idx, slot in enumerate(quiz_slots):
        key_concept = _KEY_CONCEPTS[idx % len(_KEY_CONCEPTS)]
        answer_no = (idx % 5) + 1
        item_json = _quiz_item_json(slot.ordinal, key_concept, answer_no)
        _write_envelope(responses_dir, slot.slot_id, item_json)

    for slot in (s for s in slots if s.kind == "formative"):
        _write_envelope(
            responses_dir,
            slot.slot_id,
            _formative_item_json(slot.ordinal),
        )


def _formative_item_json(no: int) -> dict:
    """Minimal schema-valid formative item JSON for the canned response."""
    topic = _KEY_CONCEPTS[(no - 1) % len(_KEY_CONCEPTS)]
    return {
        "no": no,
        "chapter_no": _CHAPTER_NO,
        "topic": topic,
        "question": f"{no}번 형성문항: {topic} 원리를 200자 내외로 서술하시오.",
        "limit": "200자 내외",
        "model_answer": f"{topic}는 교재에 따르면 핵심 과정이다.",
        "purpose": f"{topic} 이해 여부 확인.",
        "keywords": [topic, "분압", "확산"],
        "rubric_high": f"{topic} 핵심 개념 전부.",
        "rubric_mid": f"{topic} 일부 포함.",
        "rubric_low": f"{topic} 핵심 누락.",
        "support_high": f"{topic}를 다음 심화 개념으로 잇는 도약 활동.",
        "support_mid": f"{topic} 복습 지도.",
        "support_low": f"{topic} 기본 재학습 안내.",
    }


def _write_envelope(responses_dir: Path, slot_id: str, item_json: dict) -> None:
    """Write a ``responses/{slot_id}.json`` envelope for the SubscriptionBackend."""
    envelope = {
        "slot_id": slot_id,
        "raw_text": json.dumps(item_json, ensure_ascii=False),
        "model": "canned-subscription",
    }
    (responses_dir / f"{slot_id}.json").write_text(
        json.dumps(envelope, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_us1_quiz_build_end_to_end(tmp_path: Path) -> None:
    """Full quiz build → .xls with quiz_count rows, anchored items, manifest."""
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

    items, run_dir = build(
        spec=spec,
        curriculum_map=curriculum_map,
        bronze_dir=bronze,
        data_root=data_root,
        backend=backend,
        generation_spec_path=bronze / "generation_spec.yaml",
        curriculum_map_path=bronze / "curriculum_map.yaml",
    )

    # Quiz item count.
    assert len(items) == _QUIZ_COUNT

    # Gold .xls present under run dir, with the contract name.
    xls_path = run_dir / f"QuestionUploadExcel_{_WEEK}주차.xls"
    assert xls_path.is_file(), f"expected quiz xls at {xls_path}"

    # Manifest present.
    manifest_path = run_dir / "manifest_maieutica.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["quiz_count"] == _QUIZ_COUNT
    assert manifest["week"] == _WEEK

    # ingest_report present (Silver).
    assert (silver / "ingest_report.json").is_file()

    # Per-item invariants.
    for item in items:
        assert len(item.options) == 5
        assert 1 <= item.answer_no <= 5
        for opt in item.options:
            assert 30 <= len(opt) <= 50, f"option out of window: {opt!r} ({len(opt)})"
        # SC-007: groundedness status explicitly set.
        assert item.textbook_evidence is not None
        assert item.textbook_evidence.status in ("확인", "미확인")
        # Fixture is arranged so each key_concept appears in the chapter body.
        assert item.textbook_evidence.status == "확인"

    # .xls data row count == quiz_count.
    book = xlrd.open_workbook(str(xls_path))
    sheet1 = book.sheet_by_index(1)
    assert sheet1.nrows == 1 + _QUIZ_COUNT

    # No real data/ dir touched: everything under tmp_path.
    assert str(run_dir).startswith(str(tmp_path))
