"""T054 — Integration test: determinism (US6, SC-009).

Build twice with identical inputs + identical canned responses and assert:
- ``QuestionUploadExcel_{week}주차.xls`` is byte-identical across the two runs.
- ``Ch{NN}_{chapter}_FormativeTest.xlsx`` is byte-identical across the two runs.
- ``출제후보_완전판.yaml`` is byte-identical across the two runs.
- ``manifest_maieutica.json`` is EXCLUDED (it carries ``generated_at`` which is
  intentionally non-deterministic).

T059 (byte-identical e2e gate) is folded into this test: asserts ALL Gold
outputs except the manifest are byte-identical, and documents that the manifest
is the only non-deterministic artifact.  No residual non-determinism was found
during implementation (see test docstring note).
"""

from __future__ import annotations

import json
from pathlib import Path

from maieutica.ingest.spec_load import load_curriculum_map, load_generation_spec
from maieutica.plan.slots import plan_slots
from paideia_shared.schemas import MaieuticaGenerationSpec

# ---------------------------------------------------------------------------
# Fixture constants (reuse US4 pattern)
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_QUIZ_COUNT = 3
_FORMATIVE_COUNT = 2

_KEY_CONCEPTS = ["폐포", "기관지", "가로막"]
_FORMATIVE_TOPICS = ["가스교환", "가로막"]

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
        "option_evidence": [f"{key_concept} 근거 {i}" for i in range(1, 6)],
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


def test_us6_determinism_gold_outputs_byte_identical(tmp_path: Path) -> None:
    """Build twice with identical inputs → Gold outputs (excl. manifest) are byte-identical.

    SC-009 assertion: .xls + .xlsx + 출제후보_완전판.yaml + 출제품질리포트.md are
    each byte-identical across the two runs.  ``manifest_maieutica.json`` is
    explicitly excluded — it carries ``generated_at`` (intentionally non-deterministic).

    T059 gate: this test is the byte-identical e2e gate for ALL non-manifest Gold.
    No residual non-determinism was found: the xlsx finalizer pins both
    ``<dcterms:modified>`` and ``<dcterms:created>``; the yaml writer uses
    sort_keys=True; the xls writer uses a single shared xlwt style object;
    the quality report is pure deterministic string formatting.
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

    kwargs: dict = {
        "spec": spec,
        "curriculum_map": curriculum_map,
        "bronze_dir": bronze,
        "data_root": data_root,
        "backend": backend,
        "generation_spec_path": bronze / "generation_spec.yaml",
        "curriculum_map_path": bronze / "curriculum_map.yaml",
    }

    # Run 1
    _, run_dir1 = build(**kwargs)

    xls1 = (run_dir1 / f"QuestionUploadExcel_{_WEEK}주차.xls").read_bytes()
    xlsx1 = (run_dir1 / f"Ch{_CHAPTER_NO:02d}_{_CHAPTER}_FormativeTest.xlsx").read_bytes()
    yaml1 = (run_dir1 / "출제후보_완전판.yaml").read_bytes()
    report1 = (run_dir1 / "출제품질리포트.md").read_bytes()

    # Run 2 (same kwargs — run_id is deterministic so run_dir is the same path)
    _, run_dir2 = build(**kwargs)
    assert run_dir1 == run_dir2, "run_id is non-deterministic (unexpected)"

    xls2 = (run_dir2 / f"QuestionUploadExcel_{_WEEK}주차.xls").read_bytes()
    xlsx2 = (run_dir2 / f"Ch{_CHAPTER_NO:02d}_{_CHAPTER}_FormativeTest.xlsx").read_bytes()
    yaml2 = (run_dir2 / "출제후보_완전판.yaml").read_bytes()
    report2 = (run_dir2 / "출제품질리포트.md").read_bytes()

    assert xls1 == xls2, "quiz .xls is not byte-identical across runs (SC-009 violation)"
    assert xlsx1 == xlsx2, "formative .xlsx is not byte-identical across runs (SC-009 violation)"
    assert yaml1 == yaml2, (
        "출제후보_완전판.yaml is not byte-identical across runs (SC-009 violation)"
    )
    assert report1 == report2, (
        "출제품질리포트.md is not byte-identical across runs (SC-009 violation)"
    )

    # Manifest is the ONLY non-deterministic artifact — confirm it exists but
    # do NOT assert byte-identity (generated_at changes each run).
    manifest_path = run_dir1 / "manifest_maieutica.json"
    assert manifest_path.is_file(), "manifest_maieutica.json missing"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "generated_at" in manifest, "manifest missing generated_at field"
