"""T036 — Integration test: leap hardening (US2).

Builds via ``maieutica.pipeline.build`` (reusing the US1 fixture pattern) with a
``SubscriptionBackend`` fed by canned per-slot responses, then asserts the US2
hardening behaviour:

- the LMS ``.xls`` 답안설명 column == the BASIC fold ``{wrong} ─ 도약 ─ {leap}``
  with the default (unlimited) ``answer_explanation_max``;
- wrong & leap each <=200 chars → ``explanation_length_ok`` flagged True;
- ``출제후보_완전판.yaml`` exists and its ``leap.text`` is the FULL original leap;
- round-trip: splitting ``answer_explanation_combined`` on ``─ 도약 ─`` recovers
  wrong + leap.
"""

from __future__ import annotations

import json
from pathlib import Path

import xlrd
import yaml
from maieutica.ingest.spec_load import load_curriculum_map, load_generation_spec
from maieutica.output.quiz_xls import QUIZ_HEADERS
from maieutica.plan.slots import plan_slots
from paideia_shared.schemas import MaieuticaGenerationSpec

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_QUIZ_COUNT = 3
_FORMATIVE_COUNT = 1
_SEP = " ─ 도약 ─ "

_KEY_CONCEPTS = ["폐포", "기관지", "가로막"]

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


def test_us2_leap_fold_end_to_end(tmp_path: Path) -> None:
    """Default build: .xls 답안설명 is the basic fold; full yaml keeps full leap."""
    from maieutica.generate.backend import SubscriptionBackend
    from maieutica.pipeline import build

    bronze, data_root = _build_bronze(tmp_path)
    spec = load_generation_spec(bronze / "generation_spec.yaml")
    curriculum_map = load_curriculum_map(bronze / "curriculum_map.yaml")

    silver = data_root / "silver" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    responses_dir = silver / "responses"
    _write_canned_responses(responses_dir)
    backend = SubscriptionBackend(
        staging_dir=silver / "staging", responses_dir=responses_dir
    )

    items, run_dir = build(
        spec=spec,
        curriculum_map=curriculum_map,
        bronze_dir=bronze,
        data_root=data_root,
        backend=backend,
        generation_spec_path=bronze / "generation_spec.yaml",
        curriculum_map_path=bronze / "curriculum_map.yaml",
    )

    assert len(items) == _QUIZ_COUNT

    # ----- .xls 답안설명 column == basic fold (default unlimited) -----
    xls_path = run_dir / f"QuestionUploadExcel_{_WEEK}주차.xls"
    assert xls_path.is_file()
    book = xlrd.open_workbook(str(xls_path))
    sheet1 = book.sheet_by_index(1)
    col = {h: i for i, h in enumerate(QUIZ_HEADERS)}
    expl_col = col["답안설명"]
    by_item = {item.item_no: item for item in items}
    for row in range(1, sheet1.nrows):
        item_no = int(sheet1.cell(row, col["문제번호"]).value)
        item = by_item[item_no]
        cell = sheet1.cell(row, expl_col).value
        # Basic fold, untruncated.
        assert cell == item.answer_explanation_combined
        assert cell == f"{item.wrong_explanation}{_SEP}{item.leap.text}"
        # wrong & leap each <=200 → flagged ok.
        assert len(item.wrong_explanation) <= 200
        assert len(item.leap.text) <= 200
        assert item.explanation_length_ok is True

    # ----- 출제후보_완전판.yaml exists; leap.text is the FULL original -----
    full_yaml = run_dir / "출제후보_완전판.yaml"
    assert full_yaml.is_file()
    doc = yaml.safe_load(full_yaml.read_text(encoding="utf-8"))
    # T048: top-level structure is {quiz: [...], formative: [...]}.
    assert isinstance(doc, dict), "yaml must be a mapping with 'quiz'/'formative' keys"
    assert "quiz" in doc
    yaml_items = doc["quiz"]
    assert len(yaml_items) == _QUIZ_COUNT
    yaml_by_no = {d["item_no"]: d for d in yaml_items}
    for item in items:
        d = yaml_by_no[item.item_no]
        assert d["leap"]["text"] == item.leap.text  # full, untruncated

        # Round-trip split on the separator recovers wrong + leap.
        combined = d["answer_explanation_combined"]
        recovered_wrong, recovered_leap = combined.split(_SEP, 1)
        assert recovered_wrong == item.wrong_explanation
        assert recovered_leap == item.leap.text
