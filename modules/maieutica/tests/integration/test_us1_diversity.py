"""T014 — Integration test: US1 anchor diversity (SC-001 / SC-002).

Exercises ``maieutica.pipeline.build`` end-to-end on a synthetic multi-subsection
chapter with ``quiz_count = 12``, a ``SubscriptionBackend`` fed by canned per-slot
responses, and verifies the diversity contract on the ADOPTED quiz set:

- **SC-001** — every adopted item's answer anchor
  ``(textbook_evidence.chunk_id, textbook_evidence.line)`` is DISTINCT (no
  anchor-duplicate survives ``detect_duplicates``).
- **SC-002** — adopted items span ≥2 distinct subsections, and no single
  subsection hosts more than 3 adopted items (cap ``_SUBSECTION_CAP``).

To make each canned item's CORRECT-option evidence anchor inside its ASSIGNED
subsection, the test mirrors the pipeline's assignment up front: it chunks the
chapter, runs ``assign_subsections`` over the quiz slots, and writes each slot's
canned ``option_evidence[answer_no - 1]`` as a verbatim line drawn from that
slot's assigned subsection body.  This keeps the fixture self-consistent with
whatever assignment the pipeline computes.

Balance / answer distribution (US2) and 미확인-exclusion (US3) are out of scope
here — this test is focused purely on anchor diversity.
"""

from __future__ import annotations

import json
from pathlib import Path

from maieutica.ingest.spec_load import load_curriculum_map, load_generation_spec
from maieutica.plan.slots import assign_subsections, plan_slots
from maieutica.silver.chunk import chunk_chapter
from paideia_shared.schemas import MaieuticaGenerationSpec

# ---------------------------------------------------------------------------
# Fixture content — a chapter with ≥5 numbered subsections, each with verbatim
# body sentences usable as per-slot answer evidence.
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_QUIZ_COUNT = 12
_FORMATIVE_COUNT = 1

_CHAPTER_TXT = "\n".join(
    [
        "8장 호흡계통",
        "",
        "1. 코의 구조",
        "코는 들이마신 공기를 데우고 가습하는 첫 관문이다.",
        "코털과 점막은 먼지와 이물질을 거른다.",
        "코안은 비중격으로 좌우가 나뉜다.",
        "",
        "2. 인두와 후두",
        "인두는 공기와 음식이 함께 지나가는 통로이다.",
        "후두는 발성을 담당하며 기도를 보호한다.",
        "성대는 공기 흐름으로 진동하여 소리를 만든다.",
        "",
        "3. 기관과 기관지",
        "기관은 후두에서 갈라져 좌우 폐로 이어진다.",
        "기관지는 공기를 좌우 폐로 나누어 전달하는 통로이다.",
        "기관지는 점점 가늘어져 세기관지가 된다.",
        "",
        "4. 폐포와 가스 교환",
        "폐포는 모세혈관과 맞닿아 가스를 교환한다.",
        "폐포에서는 산소가 혈액으로 들어가고 이산화탄소가 나온다.",
        "이 교환은 분압 차이에 따른 단순 확산으로 일어난다.",
        "",
        "5. 호흡의 조절",
        "가로막은 수축하여 흉강의 부피를 늘리고 압력을 낮춘다.",
        "숨뇌의 호흡중추가 기본 리듬을 만든다.",
        "화학수용체가 이산화탄소 농도를 감지해 호흡수를 바꾼다.",
        "",
    ]
)


def _spec() -> MaieuticaGenerationSpec:
    """Build the validated generation spec for this fixture chapter."""
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


def _quiz_item_json(item_no: int, evidence_line: str, answer_no: int) -> dict:
    """Build a schema-valid quiz item JSON whose CORRECT option's evidence is
    a verbatim textbook line.

    The correct option's evidence (``option_evidence[answer_no - 1]``) is set to
    ``evidence_line`` — a sentence that appears verbatim in the slot's assigned
    subsection — so the answer-anchored, subsection-scoped groundedness check
    resolves it to ``status="확인"`` with a distinct ``(chunk_id, line)`` anchor.
    Options are padded into the 30–50 codepoint window.
    """
    options = [
        f"{marker} 보기 {item_no}-{i} 충분한 길이를 가진 보기 문장입니다 abcde"
        for i, marker in enumerate("①②③④⑤", start=1)
    ]
    option_evidence = [f"보기 {item_no}-{i} 근거" for i in range(1, 6)]
    option_evidence[answer_no - 1] = evidence_line
    return {
        "question_type": "지식축적",
        "stem_polarity": "부정형",
        "text": f"{item_no}번 문제: 다음 중 옳지 않은 것은?",
        "options": options,
        "answer_no": answer_no,
        "option_evidence": option_evidence,
        "wrong_explanation": f"{item_no}번 문항의 오답 설명입니다.",
        "leap_explanation": f"{item_no}번 다음 개념으로의 도약 설명입니다.",
        "key_concept": f"개념-{item_no}",
        "section": f"섹션-{item_no}",
    }


def _formative_item_json(no: int) -> dict:
    """Minimal schema-valid formative item JSON for the canned response."""
    topic = "폐포"
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


def _subsection_body_lines(chunk_text: str) -> list[str]:
    """Return the non-heading body lines of a chunk's text (verbatim anchors)."""
    lines = [ln for ln in chunk_text.splitlines() if ln.strip()]
    # The first line of each chunk is its section heading; the rest are body
    # sentences usable as verbatim evidence.
    return lines[1:] if len(lines) > 1 else lines


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
                "sections": [
                    "1. 코의 구조",
                    "2. 인두와 후두",
                    "3. 기관과 기관지",
                    "4. 폐포와 가스 교환",
                    "5. 호흡의 조절",
                ],
            }
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        json.dumps(curriculum, ensure_ascii=False), encoding="utf-8"
    )
    return bronze, data_root


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


def _write_canned_responses(responses_dir: Path) -> None:
    """Write canned per-slot responses anchored in each slot's ASSIGNED subsection.

    Mirrors the pipeline's assignment (chunk → assign_subsections) so each quiz
    slot's correct-option evidence is a DISTINCT verbatim line drawn from the
    subsection the pipeline will assign that slot to.  Distinct evidence lines →
    distinct anchors (SC-001); subsection spread → SC-002.
    """
    responses_dir.mkdir(parents=True, exist_ok=True)
    spec = _spec()

    raw_lines = _CHAPTER_TXT.splitlines()
    chunks = chunk_chapter(
        raw_lines,
        chapter_no=_CHAPTER_NO,
        chapter=_CHAPTER,
        semester=_SEMESTER,
        course_slug=_COURSE,
        source_file=f"{_CHAPTER} 호흡.txt",
    )
    chunk_by_id = {c.chunk_id: c for c in chunks}

    slots = plan_slots(spec)
    quiz_slots = [s for s in slots if s.kind == "quiz"]
    assigned = assign_subsections(quiz_slots, chunks)

    # Per-subsection cursor so each slot in a subsection draws a DISTINCT body
    # line (intra_ordinal order) → distinct anchors within the subsection.
    body_cursor: dict[str, int] = {}
    for slot in assigned:
        chunk = chunk_by_id[slot.subsection_chunk_id]
        body = _subsection_body_lines(chunk.text)
        idx = body_cursor.get(slot.subsection_chunk_id, 0)
        evidence_line = body[idx % len(body)]
        body_cursor[slot.subsection_chunk_id] = idx + 1
        answer_no = ((slot.ordinal - 1) % 5) + 1
        item_json = _quiz_item_json(slot.ordinal, evidence_line, answer_no)
        _write_envelope(responses_dir, slot.slot_id, item_json)

    for slot in (s for s in slots if s.kind == "formative"):
        _write_envelope(responses_dir, slot.slot_id, _formative_item_json(slot.ordinal))


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_us1_diversity_distinct_anchors_and_spread(tmp_path: Path) -> None:
    """Adopted items: distinct anchors (SC-001), ≥2 subsections, ≤3 each (SC-002)."""
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

    items, _run_dir = build(
        spec=spec,
        curriculum_map=curriculum_map,
        bronze_dir=bronze,
        data_root=data_root,
        backend=backend,
        generation_spec_path=bronze / "generation_spec.yaml",
        curriculum_map_path=bronze / "curriculum_map.yaml",
    )

    # All adopted items resolved to a confirmed anchor (the fixture arranges so).
    anchors = [
        (i.textbook_evidence.chunk_id, i.textbook_evidence.line)
        for i in items
        if i.textbook_evidence is not None and i.textbook_evidence.status == "확인"
    ]
    assert anchors, "expected at least some confirmed anchors"

    # SC-001: every adopted anchor is distinct (0 anchor-duplicates survive).
    assert len(anchors) == len(set(anchors)), f"duplicate anchors: {anchors}"

    # SC-002: adopted items span ≥2 distinct subsections.
    subsections = {chunk_id for chunk_id, _ in anchors}
    assert len(subsections) >= 2, f"only {len(subsections)} subsection(s) covered"

    # SC-002: no subsection hosts more than 3 adopted items.
    per_subsection: dict[str, int] = {}
    for chunk_id, _ in anchors:
        per_subsection[chunk_id] = per_subsection.get(chunk_id, 0) + 1
    assert all(v <= 3 for v in per_subsection.values()), per_subsection

    # Exact adopted count: the fixture chapter yields 5 subsections, so capacity
    # is min(12, 3*5) = 12 — all N slots are assigned. Every canned correct-option
    # evidence is a distinct verbatim subsection line → all 확인 with distinct
    # anchors, so dedup removes none and the adopted set is exactly N.
    assert len(items) == _QUIZ_COUNT
