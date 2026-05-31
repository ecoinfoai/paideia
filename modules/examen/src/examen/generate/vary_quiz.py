"""T041 — Quiz variation generation: vary_quiz.

``vary_quiz(entry, backend, cache) -> ExamItemDraft``

Converts a quiz ``SourceInventoryEntry`` into a varied ``ExamItemDraft``
following the R8 variation criterion:

- Keep the SAME 교재 근거 (textbook reference) + SAME 정답 판정 포인트
  (the concept the original tests).
- REWRITE 발문 and 보기 wording so it is neither identical nor wholly
  different from the original.

Design mirrors ``convert_formative``:
1. Build a generation prompt from the entry's original stem + options + answer.
2. Call ``cache.generate(request)`` — deterministic via InputHashCache.
3. Parse JSON response → ``ExamItemDraft(source="quiz", ...)``.

Expected LLM response shape (JSON, UTF-8)::

    {
      "question_type": "지식축적" | "맥락통찰",
      "difficulty":    "1_쉬움" | "2_보통" | "3_어려움",
      "stem_polarity": "부정형" | "긍정형",
      "text":          "<varied 발문>",
      "options":       ["<①>", "<②>", "<③>", "<④>", "<⑤>"],
      "answer_no":     1~5,
      "distractor_rationale": ["<①근거>", ..., "<⑤근거>"],
      "wrong_explanation": "<270~330자>",
      "leap_explanation":  "<270~330자>",
      "intent":        "<40~60자>",
      "key_concept":   "<1~3단어 핵심개념>"
    }

Usage::

    from examen.generate.vary_quiz import vary_quiz

    item = vary_quiz(entry=entry, backend=backend, cache=cache)
"""

from __future__ import annotations

import json
import re

from paideia_shared.schemas import ExamItemDraft, SourceInventoryEntry

from examen.generate.backend import GenerationRequest, InputHashCache, LLMBackend

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
[퀴즈 변형 지시]

다음 객관식 퀴즈 문제를 변형하라.
출처: {source_ref}
원본 정답: {original_answer}번

[원본 발문]
{stem}

[원본 보기]
{options_text}

[변형 규칙]
1. 동일한 교재 근거(절)와 동일한 정답 판정 개념을 유지한다.
2. 발문과 보기 표현을 재작성한다 — 원본과 자구 동일 금지.
3. 정답 판정 포인트(어떤 개념이 틀린/맞는지)는 바꾸지 않는다.
4. 보기는 5개 (원본 정답 번호와 동일한 위치에 정답 배치 권장, 단 변경 가능).
5. 근거는 반드시 교재 내용만 사용 — 외부 지식 금지.
6. 보기 각 30~40자 권장.

[JSON 출력 형식]
{{
  "question_type": "지식축적",
  "difficulty": "2_보통",
  "stem_polarity": "부정형",
  "text": "<변형된 발문>",
  "options": ["①...", "②...", "③...", "④...", "⑤..."],
  "answer_no": <정답 보기 번호 1~5>,
  "distractor_rationale": ["①근거", "②근거", "③근거", "④근거", "⑤근거"],
  "wrong_explanation": "<270~330자 오답 설명>",
  "leap_explanation": "<270~330자 도약 설명>",
  "intent": "<40~60자 출제 의도>",
  "key_concept": "<1~3단어 핵심개념>"
}}
"""


def _build_prompt(entry: SourceInventoryEntry) -> str:
    """Build the variation prompt from a quiz SourceInventoryEntry.

    Args:
        entry: The quiz source inventory entry with stem, options, and answer.

    Returns:
        Formatted prompt string for the LLM.
    """
    options = entry.options or []
    options_text = "\n".join(
        f"{i+1}. {opt}" for i, opt in enumerate(options)
    )
    return _PROMPT_TEMPLATE.format(
        source_ref=entry.source_ref,
        original_answer=entry.answer or "?",
        stem=entry.stem,
        options_text=options_text or "(보기 없음)",
    )


# ---------------------------------------------------------------------------
# Response parsing (mirrors convert_formative)
# ---------------------------------------------------------------------------


def _parse_variation_response(
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
            f"vary_quiz: LLM response for {source_ref!r} is not valid JSON. "
            f"Error: {exc}. Raw (first 200 chars): {raw_text[:200]!r}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"vary_quiz: LLM response for {source_ref!r} parsed as "
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
            f"vary_quiz: {source_ref!r} has a malformed 'answer_no' "
            f"value {value!r} (expected 1-5)."
        ) from exc


def _source_ref_to_slot_id(source_ref: str) -> str:
    """Convert quiz source_ref to a valid slot_id string.

    E.g. ``'퀴즈:9주#3'`` → ``'quiz-9-3'``.

    Args:
        source_ref: SourceInventoryEntry.source_ref.

    Returns:
        ASCII-safe slot_id string.
    """
    # 퀴즈:9주#3 → quiz-9-3
    clean = source_ref.replace("퀴즈:", "quiz-").replace("주#", "-").replace("주", "")
    # Remove any remaining non-alphanumeric chars except hyphen
    clean = re.sub(r"[^a-zA-Z0-9\-]", "", clean)
    return clean or "quiz-unknown"


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
# Public API
# ---------------------------------------------------------------------------


def vary_quiz(
    entry: SourceInventoryEntry,
    backend: LLMBackend,
    cache: InputHashCache,
) -> ExamItemDraft:
    """Generate a varied quiz item from a quiz SourceInventoryEntry.

    Instructs the LLM to:
    - Keep the same educational concept and correct-answer judgment point.
    - Rewrite the stem and option wording (neither identical nor wholly different).

    Deterministic via InputHashCache.  Backend-isolated (any LLMBackend).

    Args:
        entry: Quiz source inventory entry (must have source="quiz").
        backend: LLM backend (used on cache miss only).
        cache: InputHashCache wrapping the backend.

    Returns:
        Schema-valid ExamItemDraft with source="quiz" and source_ref=entry.source_ref.

    Raises:
        ValueError: If entry.source != "quiz", or if the LLM response
            cannot be parsed.
    """
    if entry.source != "quiz":
        raise ValueError(
            f"vary_quiz: entry.source must be 'quiz', "
            f"got {entry.source!r} (source_ref={entry.source_ref!r})"
        )

    # Step 1: build prompt
    prompt = _build_prompt(entry)

    # Step 2: build generation request
    slot_id = _source_ref_to_slot_id(entry.source_ref)
    request = GenerationRequest(
        slot_id=slot_id,
        prompt=prompt,
        context_refs=[entry.source_ref],
        metadata={
            "source": "quiz",
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
    item_data = _parse_variation_response(response.raw_text, source_ref=entry.source_ref)

    # Step 5: extract and validate fields
    answer_no = _parse_answer_no(item_data.get("answer_no", 1), source_ref=entry.source_ref)

    question_type = item_data.get("question_type", "지식축적")
    if question_type not in ("지식축적", "맥락통찰"):
        question_type = "지식축적"

    stem_polarity = item_data.get("stem_polarity", "부정형")
    if stem_polarity not in ("부정형", "긍정형"):
        stem_polarity = "부정형"

    difficulty = item_data.get("difficulty", "2_보통")
    if difficulty not in ("1_쉬움", "2_보통", "3_어려움"):
        difficulty = "2_보통"

    options = item_data.get("options", [])
    option_length_ok = _check_option_lengths(options)

    # item_no: extract numeric part from slot_id (e.g. 'quiz-9-3' → 3)
    try:
        parts = slot_id.rsplit("-", 1)
        item_no = max(1, int(parts[1])) if len(parts) == 2 else 1
    except (ValueError, IndexError):
        item_no = 1

    chapter_no = entry.chapter_no or 0
    chapter = f"{chapter_no}장"  # minimal stable label; pipeline overrides

    # Step 6: assemble ExamItemDraft
    return ExamItemDraft(
        semester=entry.semester,
        course_slug=entry.course_slug,
        item_no=item_no,
        source="quiz",
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
        distractor_rationale=item_data.get("distractor_rationale", []),
        wrong_explanation=item_data.get("wrong_explanation", ""),
        leap_explanation=item_data.get("leap_explanation", ""),
        textbook_evidence=None,  # 퀴즈 변형 — 교재 근거 앵커 없음
        intent=item_data.get("intent", ""),
        option_length_ok=option_length_ok,
        duplicate_flag=False,
        review_note="",
        adoption_status="생성",
        note=None,
    )


__all__ = ["vary_quiz"]
