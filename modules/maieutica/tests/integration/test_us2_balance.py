"""T022 — Integration test: US2 answer-key balance + determinism (SC-003 / SC-004).

Exercises ``maieutica.pipeline.build`` end-to-end on a synthetic multi-subsection
chapter where EVERY canned quiz item carries ``answer_no = 3`` — the v0.1.0
pathology where the model parks the correct option in the same slot every time.
The pipeline must, AFTER anchor-dedup and BEFORE output, run
``balance_answer_keys`` so the adopted set's answer positions are balanced and the
LMS ``.xls`` is upload-ready without manual answer shuffling.

Asserts on the ADOPTED quiz set:

- **SC-003 ①** — no answer_no value appears 3-in-a-row (max consecutive run ≤ 2).
- **SC-003 ②** — no single answer_no value exceeds 50% of the adopted set.
- **SC-004** — running ``build`` twice on identical inputs yields byte-identical
  quiz ``.xls`` files (balance is deterministic; no RNG).
- **content preservation** — balance only moves option POSITIONS: each item still
  carries 5 options / 5 option_evidence and the V4 fold holds.

Diversity (US1) and 미확인-exclusion (US3) are out of scope here.

To make each canned item's CORRECT-option evidence anchor inside its ASSIGNED
subsection (so items resolve to ``확인`` and survive dedup with DISTINCT anchors),
the test mirrors the pipeline's assignment up front (chunk → assign_subsections),
exactly as ``test_us1_diversity.py`` does.
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

# The pathology under test: every canned item's correct option sits at position 3.
_PATHOLOGY_ANSWER_NO = 3

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
    ``evidence_line`` — a sentence appearing verbatim in the slot's assigned
    subsection — so the answer-anchored, subsection-scoped groundedness check
    resolves it to ``status="확인"`` with a distinct ``(chunk_id, line)`` anchor.
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
    subsection the pipeline will assign that slot to (→ distinct anchors → all
    survive dedup).  EVERY item's ``answer_no`` is the pathology value
    (``_PATHOLOGY_ANSWER_NO``) so the pre-balance set is degenerate; the pipeline
    must balance it before output.
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

    body_cursor: dict[str, int] = {}
    for slot in assigned:
        chunk = chunk_by_id[slot.subsection_chunk_id]
        body = _subsection_body_lines(chunk.text)
        idx = body_cursor.get(slot.subsection_chunk_id, 0)
        evidence_line = body[idx % len(body)]
        body_cursor[slot.subsection_chunk_id] = idx + 1
        # Pathology: the correct option is always at position 3.
        item_json = _quiz_item_json(
            slot.ordinal, evidence_line, _PATHOLOGY_ANSWER_NO
        )
        _write_envelope(responses_dir, slot.slot_id, item_json)

    for slot in (s for s in slots if s.kind == "formative"):
        _write_envelope(responses_dir, slot.slot_id, _formative_item_json(slot.ordinal))


def _run_build(tmp_path: Path) -> tuple[list, Path]:
    """Lay out a fresh data_root under ``tmp_path`` and run ``build`` once."""
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
    return build(
        spec=spec,
        curriculum_map=curriculum_map,
        bronze_dir=bronze,
        data_root=data_root,
        backend=backend,
        generation_spec_path=bronze / "generation_spec.yaml",
        curriculum_map_path=bronze / "curriculum_map.yaml",
    )


def _max_consecutive_run(values: list[int]) -> int:
    """Return the longest run of identical consecutive values in ``values``."""
    if not values:
        return 0
    longest = run = 1
    for prev, cur in zip(values, values[1:], strict=False):
        run = run + 1 if cur == prev else 1
        longest = max(longest, run)
    return longest


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_us2_balance_breaks_runs_and_is_deterministic(tmp_path: Path) -> None:
    """All-③ canned set → balanced output (SC-003) and byte-identical re-run (SC-004)."""
    items, run_dir = _run_build(tmp_path / "run_a")

    assert len(items) == _QUIZ_COUNT, "fixture expected all 12 slots adopted"

    answer_seq = [i.answer_no for i in items]

    # Sanity: the pre-balance pathology would be all-③; balance must move them.
    assert set(answer_seq) != {_PATHOLOGY_ANSWER_NO}, (
        f"answers were NOT balanced — still all {_PATHOLOGY_ANSWER_NO}: {answer_seq}"
    )

    # SC-003 ①: no answer_no runs 3-in-a-row.
    assert _max_consecutive_run(answer_seq) <= 2, (
        f"max consecutive run > 2: {answer_seq}"
    )

    # SC-003 ②: no single answer_no value exceeds 50% of the adopted set.
    from collections import Counter

    counts = Counter(answer_seq)
    cap = len(answer_seq) / 2
    assert all(c <= cap for c in counts.values()), (
        f"some answer_no exceeds 50%: {dict(counts)} of {len(answer_seq)}"
    )

    # Content preservation: balance only moved positions — each item keeps its
    # 5 options / 5 option_evidence and the V4 fold (schema-enforced; sanity).
    for item in items:
        assert len(item.options) == 5
        assert len(item.option_evidence) == 5
        assert 1 <= item.answer_no <= 5

    # SC-004: a second build on identical inputs (fresh data_root) yields a
    # byte-identical quiz .xls — balance is deterministic (no RNG).
    items_b, run_dir_b = _run_build(tmp_path / "run_b")
    xls_a = (run_dir / f"QuestionUploadExcel_{_WEEK}주차.xls").read_bytes()
    xls_b = (run_dir_b / f"QuestionUploadExcel_{_WEEK}주차.xls").read_bytes()
    assert xls_a == xls_b, "re-run produced a non-identical quiz .xls (SC-004)"

    # And the balanced answer sequence is reproducible item-for-item.
    assert [i.answer_no for i in items_b] == answer_seq
