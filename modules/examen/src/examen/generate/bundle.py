"""T025 — Per-slot deterministic generation-request bundle builder.

``build_bundle`` selects the TextbookChunk(s) that match the slot's
chapter (and optionally section), then constructs a fully-specified
``GenerationRequest`` with:

- A Korean prompt that instructs the LLM to produce exactly one
  5-option, single-answer, 부정형-polarity exam question using ONLY
  the supplied textbook text (no outside knowledge).
- ``context_refs`` listing chunk IDs / source-file anchors.
- ``metadata`` carrying chapter, chapter_no, difficulty, source, and
  slot_id for downstream traceability.

The output is byte-identical for identical (slot, chunks) input because
every assembly step is deterministic (string concatenation, sorted joins).

Usage::

    from examen.generate.bundle import build_bundle

    req = build_bundle(slot, chunks)
    # req: GenerationRequest ready for backend.generate()
"""

from __future__ import annotations

from paideia_shared.schemas import TextbookChunk

from examen.generate.backend import GenerationRequest
from examen.plan.blueprint import Slot

# ---------------------------------------------------------------------------
# Prompt template components (Korean — deterministic, no f-string variation)
# ---------------------------------------------------------------------------

_PROMPT_HEADER = """\
[출제 지시]

당신은 해부생리학 전공 시험 문항을 생성하는 전문 출제 보조 시스템입니다.
아래 [교재 본문]에 제공된 텍스트만을 근거로 문항을 생성하십시오.
외부 지식이나 교재 본문 이외의 정보를 사용하지 마십시오.

[문항 형식 요건]
- 문항 형태: 5지선다형 단일 정답 (보기 5개, 정답 1개)
- 발문 방향: 부정형 ("다음 중 가장 옳지 않은 것은?")
- 각 보기 길이: 번호 포함 30~40자 (코드포인트 기준)
- 발문(stem)은 간결하고 명확하게 작성하십시오.

[난이도]
{difficulty}

[출처 정보]
장: {chapter}
절: {section}

[교재 본문]
{chunk_text}

[출력 형식 — JSON만 출력, 다른 텍스트 없음]
{{
  "question_type": "지식축적" 또는 "맥락통찰",
  "difficulty": "1_쉬움" 또는 "2_보통" 또는 "3_어려움",
  "stem_polarity": "부정형",
  "text": "<발문 전체>",
  "options": ["<보기①>", "<보기②>", "<보기③>", "<보기④>", "<보기⑤>"],
  "answer_no": <정답 보기 번호 1~5>,
  "distractor_rationale": [
    "<보기①의 오답/정답 근거>",
    "<보기②의 오답/정답 근거>",
    "<보기③의 오답/정답 근거>",
    "<보기④의 오답/정답 근거>",
    "<보기⑤의 오답/정답 근거>"
  ],
  "wrong_explanation": "<오답 설명 (틀린 학생용, 270~330자)>",
  "leap_explanation": "<도약 설명 (맞힌 학생용, 270~330자)>",
  "intent": "<출제 의도 (40~60자)>",
  "key_concept": "<핵심 개념 키워드 (1~3 단어)>"
}}
"""

_DIFFICULTY_KO: dict[str, str] = {
    "1_쉬움": "쉬움 (기본 개념 확인)",
    "2_보통": "보통 (응용 및 비교)",
    "3_어려움": "어려움 (심화 분석 및 통찰)",
}


def _select_chunks(
    slot: Slot,
    chunks: list[TextbookChunk],
) -> list[TextbookChunk]:
    """Return chunks that match the slot's chapter_no (and section if set).

    All chunks are filtered by ``chapter_no``; if the slot has a
    ``section``, further filter by exact section match.  If section
    filtering yields no chunks, fall back to all chapter-level chunks.

    Args:
        slot: The exam slot whose chapter/section we need.
        chunks: All available TextbookChunk objects (may span many chapters).

    Returns:
        Non-empty list of matching chunks, or empty list if none found.
    """
    # 챕터 번호 기준 필터
    ch_chunks = [c for c in chunks if c.chapter_no == slot.chapter_no]

    if not slot.section:
        return ch_chunks

    # 절 기준 추가 필터
    sec_chunks = [c for c in ch_chunks if c.section == slot.section]
    # 절 일치 없으면 챕터 전체 사용 (fallback)
    return sec_chunks if sec_chunks else ch_chunks


def build_bundle(
    slot: Slot,
    chunks: list[TextbookChunk],
) -> GenerationRequest:
    """Build a deterministic GenerationRequest for one exam slot.

    Steps:
    1. Select chunks matching the slot's chapter (and optional section).
    2. Concatenate chunk texts in ascending ``line_start`` order (deterministic).
    3. Format the prompt with the slot's difficulty/chapter/section info
       and the assembled chunk text.
    4. Build ``context_refs`` as ``"{source_file}#{chunk_id}"`` strings.
    5. Build ``metadata`` dict for downstream traceability.

    Args:
        slot: The planned exam slot.
        chunks: All available TextbookChunk objects.

    Returns:
        A ``GenerationRequest`` ready for ``cache.generate(request)``.
    """
    # Step 1: select relevant chunks
    selected = _select_chunks(slot, chunks)

    # Step 2: sort by line_start for deterministic ordering
    selected_sorted = sorted(selected, key=lambda c: (c.chapter_no, c.line_start))

    # Step 3: assemble chunk text (join with double newline)
    chunk_text = (
        "\n\n".join(c.text for c in selected_sorted) if selected_sorted else "(교재 본문 없음)"
    )

    # Step 4: build context_refs
    context_refs: list[str] = [f"{c.source_file}#{c.chunk_id}" for c in selected_sorted]

    # Step 5: format prompt
    section_label = slot.section if slot.section else "(전체)"
    difficulty_ko = _DIFFICULTY_KO.get(slot.difficulty, slot.difficulty)

    prompt = _PROMPT_HEADER.format(
        difficulty=difficulty_ko,
        chapter=slot.chapter,
        section=section_label,
        chunk_text=chunk_text,
    )

    # Step 6: build metadata
    metadata: dict[str, object] = {
        "chapter": slot.chapter,
        "chapter_no": slot.chapter_no,
        "difficulty": slot.difficulty,
        "source": slot.source,
        "slot_id": slot.slot_id,
        "section": slot.section,
        "chunk_ids": [c.chunk_id for c in selected_sorted],
    }

    return GenerationRequest(
        slot_id=slot.slot_id,
        prompt=prompt,
        context_refs=context_refs,
        metadata=metadata,
    )


__all__ = ["build_bundle"]
