"""T034 — Formative-to-MCQ conversion: convert_formative.

``convert_formative(entry, backend, cache) -> ExamItemDraft``

Converts a formative (서술형) ``SourceInventoryEntry`` into a 객관식
``ExamItemDraft`` following the 부정형 pattern:

- 4 CORRECT options derived from the model_answer's core propositions.
- 1 WRONG option derived from a common misconception (rubric["low"] or
  keyword inversion) — this becomes the ANSWER (``answer_no``).
- Stem uses 부정형 phrasing ("가장 옳지 않은 것은?").
- Ground truth is ONLY the model_answer + support (공유정보) + textbook;
  no outside knowledge is injected into the prompt.

Design mirrors ``item_gen.generate_item``:
1. Build a generation prompt from the entry's fields.
2. Call ``cache.generate(request)`` — deterministic via InputHashCache.
3. Parse JSON response → ``ExamItemDraft``.

Expected LLM response shape (JSON, UTF-8)::

    {
      "question_type": "지식축적" | "맥락통찰",
      "difficulty":    "1_쉬움" | "2_보통" | "3_어려움",
      "stem_polarity": "부정형",
      "text":          "<부정형 발문>",
      "options":       ["<①>", "<②>", "<③>", "<④>", "<⑤>"],
      "answer_no":     1~5,          // 틀린 보기 번호
      "distractor_rationale": ["<①근거>", ..., "<⑤근거>"],
      "wrong_explanation": "<270~330자>",
      "leap_explanation":  "<270~330자>",
      "intent":        "<40~60자>",
      "key_concept":   "<1~3단어 핵심개념>",
      "wrong_option_no": 1~5         // 틀린 보기 번호 (answer_no 와 동일)
    }

Usage::

    from examen.generate.convert_formative import convert_formative

    item = convert_formative(entry=entry, backend=backend, cache=cache)
"""

from __future__ import annotations

import json

from paideia_shared.schemas import ExamItemDraft, SourceInventoryEntry

from examen.generate.backend import GenerationRequest, InputHashCache, LLMBackend

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
[형성평가 → 객관식 변환 지시]

다음 형성평가 문항을 5지 택1 부정형 객관식으로 변환하라.
출처: {source_ref}

[원문 서술형 질문]
{stem}

[모범답안 및 공유정보]
{model_answer}

[핵심 키워드]
{keywords}

[채점 기준]
- 상: {rubric_high}
- 중: {rubric_mid}
- 하(흔한 오개념): {rubric_low}

[변환 규칙]
1. 발문: "다음 중 ... 에 대한 설명으로 가장 옳지 않은 것은?" (부정형 강제)
2. 보기 ①~⑤ 중 4개는 모범답안·공유정보에 근거한 옳은 진술(30~40자 각각)
3. 보기 1개는 채점 기준 '하'의 흔한 오개념에 기반한 틀린 진술(30~40자) — 이것이 정답
4. 틀린 보기(정답)는 ①~⑤ 중 어느 번호든 가능 (균형 분포 권장)
5. 근거는 반드시 모범답안·공유정보·교재 내용만 사용 — 외부 지식 금지

[JSON 출력 형식]
{{
  "question_type": "지식축적",
  "difficulty": "2_보통",
  "stem_polarity": "부정형",
  "text": "<발문>",
  "options": ["①...", "②...", "③...", "④...", "⑤..."],
  "answer_no": <틀린 보기 번호 1~5>,
  "distractor_rationale": ["①근거", "②근거", "③근거", "④근거", "⑤근거"],
  "wrong_explanation": "<270~330자 오답 설명>",
  "leap_explanation": "<270~330자 도약 설명>",
  "intent": "<40~60자 출제 의도>",
  "key_concept": "<1~3단어 핵심개념>",
  "wrong_option_no": <틀린 보기 번호 — answer_no 와 동일>
}}
"""


def _build_prompt(entry: SourceInventoryEntry) -> str:
    """Build the generation prompt from a SourceInventoryEntry.

    Args:
        entry: The formative question entry with model_answer and rubric.

    Returns:
        Formatted prompt string for the LLM.
    """
    rubric = entry.rubric or {}
    return _PROMPT_TEMPLATE.format(
        source_ref=entry.source_ref,
        stem=entry.stem,
        model_answer=entry.model_answer or "(모범답안 없음)",
        keywords=", ".join(entry.keywords) if entry.keywords else "(없음)",
        rubric_high=rubric.get("high", "-"),
        rubric_mid=rubric.get("mid", "-"),
        rubric_low=rubric.get("low", "-"),
    )


# ---------------------------------------------------------------------------
# Response parsing (mirrors item_gen._parse_response)
# ---------------------------------------------------------------------------


def _parse_formative_response(
    raw_text: str,
    source_ref: str,
) -> dict:  # type: ignore[type-arg]
    """Parse the LLM's raw_text as JSON.

    Strips optional markdown code fences (```json ... ```).

    Args:
        raw_text: Raw string from the backend.
        source_ref: Source reference for error messages.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If the response is not valid JSON or not a dict.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:] if lines[-1].strip() == "```" else lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"convert_formative: LLM response for {source_ref!r} is not valid JSON. "
            f"Error: {exc}. Raw (first 200 chars): {raw_text[:200]!r}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"convert_formative: LLM response for {source_ref!r} parsed as "
            f"{type(data).__name__}, expected dict."
        )
    return data


def _parse_answer_no(value: object, source_ref: str) -> int:
    """Coerce answer_no to int, raising a located error on failure.

    Args:
        value: Raw answer_no from the parsed response.
        source_ref: Source reference for error messages.

    Returns:
        Integer answer number.

    Raises:
        ValueError: If not coercible to int.
    """
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"convert_formative: {source_ref!r} has a malformed 'answer_no' "
            f"value {value!r} (expected 1-5)."
        ) from exc


def _check_option_lengths(options: list[str]) -> bool:
    """Check that all options are 30–40 codepoints.

    Args:
        options: List of option strings.

    Returns:
        True iff all options satisfy 30 <= len(opt) <= 40.
    """
    if not options:
        return False
    return all(30 <= len(opt) <= 40 for opt in options)


# ---------------------------------------------------------------------------
# Slot-ID helper (formative items use source_ref as pseudo-slot)
# ---------------------------------------------------------------------------


def _source_ref_to_slot_id(source_ref: str) -> str:
    """Convert source_ref to a valid slot_id string.

    E.g. ``'형성평가:8장#1'`` → ``'formative-8-1'``.

    Args:
        source_ref: SourceInventoryEntry.source_ref.

    Returns:
        ASCII-safe slot_id string.
    """
    # 형성평가:8장#1 → formative-8-1
    clean = source_ref.replace("형성평가:", "formative-").replace("장#", "-").replace("장", "")
    # Remove any remaining non-alphanumeric chars except hyphen
    import re
    clean = re.sub(r"[^a-zA-Z0-9\-]", "", clean)
    return clean or "formative-unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def convert_formative(
    entry: SourceInventoryEntry,
    backend: LLMBackend,
    cache: InputHashCache,
) -> ExamItemDraft:
    """Convert a formative SourceInventoryEntry to an ExamItemDraft.

    Builds a generation request instructing the LLM to:
    - Create 4 correct options from the model_answer's core propositions.
    - Create 1 wrong option from rubric["low"] / keyword inversion.
    - Use 부정형 stem ("가장 옳지 않은 것은?").
    - Set answer_no to the wrong option's position.

    Args:
        entry: Formative question entry (must have source="formative").
        backend: LLM backend (used on cache miss only).
        cache: InputHashCache wrapping the backend.

    Returns:
        Schema-valid ExamItemDraft with source="formative", stem_polarity=
        "부정형", and answer_no pointing to the wrong option.

    Raises:
        ValueError: If entry.source != "formative", or if the LLM response
            cannot be parsed.
    """
    if entry.source != "formative":
        raise ValueError(
            f"convert_formative: entry.source must be 'formative', "
            f"got {entry.source!r} (source_ref={entry.source_ref!r})"
        )

    # Step 1: build prompt
    prompt = _build_prompt(entry)

    # Step 2: build generation request (slot_id from source_ref for cache key)
    slot_id = _source_ref_to_slot_id(entry.source_ref)
    request = GenerationRequest(
        slot_id=slot_id,
        prompt=prompt,
        context_refs=[entry.source_ref],
        metadata={
            "source": "formative",
            "source_ref": entry.source_ref,
            "chapter_no": entry.chapter_no,
            "week": entry.week,
            "semester": entry.semester,
            "course_slug": entry.course_slug,
        },
    )

    # Step 3: call cache (→ backend on miss)
    response = cache.generate(request)

    # Step 4: parse structured JSON
    item_data = _parse_formative_response(response.raw_text, source_ref=entry.source_ref)

    # Step 5: extract and validate fields
    answer_no = _parse_answer_no(
        item_data.get("answer_no", item_data.get("wrong_option_no", 1)),
        source_ref=entry.source_ref,
    )

    question_type = item_data.get("question_type", "지식축적")
    if question_type not in ("지식축적", "맥락통찰"):
        question_type = "지식축적"

    # stem_polarity 강제: 형성 변환은 항상 부정형
    stem_polarity = "부정형"

    difficulty = item_data.get("difficulty", "2_보통")
    if difficulty not in ("1_쉬움", "2_보통", "3_어려움"):
        difficulty = "2_보통"

    options = item_data.get("options", [])
    option_length_ok = _check_option_lengths(options)

    distractor_rationale = item_data.get("distractor_rationale", [])

    # item_no: extract numeric part from slot_id
    try:
        parts = slot_id.rsplit("-", 1)
        item_no = max(1, int(parts[1])) if len(parts) == 2 else 1
    except (ValueError, IndexError):
        item_no = 1

    # chapter: use chapter_no; chapter name not available without curriculum_map
    # — use source_ref prefix as a stable chapter label
    chapter_no = entry.chapter_no or 0
    chapter = f"{chapter_no}장"  # minimal stable label; pipeline may override

    # Step 6: assemble ExamItemDraft
    return ExamItemDraft(
        semester=entry.semester,
        course_slug=entry.course_slug,
        item_no=item_no,
        source="formative",
        source_ref=entry.source_ref,
        chapter=chapter,
        chapter_no=chapter_no,
        section=None,
        week=entry.week,
        key_concept=item_data.get("key_concept"),
        is_emphasized=None,
        emphasis_class_count=None,
        question_type=question_type,
        bloom=None,
        difficulty=difficulty,
        stem_polarity=stem_polarity,
        text=item_data.get("text", ""),
        options=options,
        answer_no=answer_no,
        distractor_rationale=distractor_rationale,
        wrong_explanation=item_data.get("wrong_explanation", ""),
        leap_explanation=item_data.get("leap_explanation", ""),
        textbook_evidence=None,  # 형성 변환 — 교재 근거 앵커 없음
        intent=item_data.get("intent", ""),
        option_length_ok=option_length_ok,
        duplicate_flag=False,
        review_note="",
        adoption_status="생성",
        note=None,
    )


__all__ = ["convert_formative"]
