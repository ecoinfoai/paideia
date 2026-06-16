"""T027 — Quiz candidate generation via LLM backend (US1).

``generate_quiz_item`` runs the per-slot quiz-generation flow:

1. Build the generation bundle (T026 :func:`~maieutica.generate.bundle.build_bundle`).
2. Call ``cache.generate(request)`` — the cache guarantees byte-identical
   re-runs; the backend is only called on a cache miss.
3. Parse the LLM's structured JSON response and assemble a COMPLETE,
   schema-valid :class:`~paideia_shared.schemas.QuizItemCandidate`.

Staged-enrichment contract
--------------------------
``QuizItemCandidate`` is ``frozen=True`` and requires every field at
construction.  This function builds a fully valid candidate; later pipeline
stages enrich specific fields via ``model_copy(update=...)`` (examen pattern):

- ``difficulty`` is set PROVISIONALLY to ``"중"`` and finalized
  deterministically by ``assemble/difficulty`` (T030).
- ``textbook_evidence`` is ``None`` and grounded by ``verify/groundedness``
  (T028).
- ``leap.textbook_evidence`` is ``None`` and grounded by T037/T038.

``question_type`` follows the N1 decision: the LLM emits it and this code
validates it against ``Literal["지식축적", "맥락통찰"]``, falling back
deterministically to ``"지식축적"`` when missing/invalid (never raising).

Expected LLM response shape (JSON, UTF-8)::

    {
      "question_type":     "지식축적" | "맥락통찰",
      "stem_polarity":     "부정형" | "긍정형",
      "text":              "<발문>",
      "options":           ["<①>", ..., "<⑤>"],
      "answer_no":         1-5,
      "option_evidence":   ["<①근거>", ..., "<⑤근거>"],
      "wrong_explanation": "<오답 설명>",
      "leap_explanation":  "<도약 설명>",
      "key_concept":       "<핵심개념>",
      "section":           "<절>"
    }

Usage::

    from maieutica.generate.quiz_gen import generate_quiz_item

    item = generate_quiz_item(slot, spec, chunks, cache)
"""

from __future__ import annotations

import json
from typing import Any

from paideia_shared.schemas import (
    LeapExplanation,
    MaieuticaGenerationSpec,
    QuizItemCandidate,
    TextbookChunk,
)

from maieutica.generate.backend import InputHashCache
from maieutica.generate.bundle import build_bundle
from maieutica.plan.slots import Slot

_VALID_QUESTION_TYPES = ("지식축적", "맥락통찰")
_DEFAULT_QUESTION_TYPE = "지식축적"
_VALID_STEM_POLARITY = ("부정형", "긍정형")
_DEFAULT_STEM_POLARITY = "부정형"

# Cross-module sentinel: a per-option evidence string the LLM did not supply.
# verify/groundedness (T028) imports this and treats such entries as 미확인.
MISSING_EVIDENCE_PLACEHOLDER = "(근거 미기재)"

# Soft-flag thresholds (incl. spaces / codepoints).
_OPTION_MIN_LEN = 30
_OPTION_MAX_LEN = 50
_EXPLANATION_MAX_LEN = 200


def generate_quiz_item(
    slot: Slot,
    spec: MaieuticaGenerationSpec,
    chunks: list[TextbookChunk],
    cache: InputHashCache,
    avoid_list: list[str] | None = None,
) -> QuizItemCandidate:
    """Generate one quiz candidate for a quiz slot via the LLM backend.

    Args:
        slot: The planned quiz slot.
        spec: The generation specification (identity / chapter labels).
        chunks: All available TextbookChunk objects (filtered by bundle).
        cache: InputHashCache wrapping the backend (invoked on cache miss).
        avoid_list: Prior same-subsection answer-points the model must NOT
            re-ask, in the order they were asked (US1/R4). ``None`` is treated
            as empty, keeping the dry-run / CLI callers (which pass none)
            working. It is threaded into ``build_bundle`` and so participates in
            the cache key, preserving byte-identical re-runs.

    Returns:
        A complete, schema-valid :class:`~paideia_shared.schemas.QuizItemCandidate`
        with provisional ``difficulty="중"`` and ``textbook_evidence=None``.

    Raises:
        ValueError: If the LLM response is not valid JSON, is not a JSON object,
            or carries a malformed ``answer_no``.
    """
    request = build_bundle(slot, spec, chunks, avoid_list=avoid_list)
    response = cache.generate(request)
    data = _parse_response(response.raw_text, slot_id=slot.slot_id)

    options: list[str] = list(data.get("options", []))
    option_evidence = _normalize_option_evidence(data.get("option_evidence"), options)

    wrong_explanation = str(data.get("wrong_explanation", ""))
    leap = LeapExplanation(
        text=str(data.get("leap_explanation", "")),
        textbook_evidence=None,  # grounded later (T037/T038)
    )
    combined = f"{wrong_explanation} ─ 도약 ─ {leap.text}"

    question_type = data.get("question_type", _DEFAULT_QUESTION_TYPE)
    if question_type not in _VALID_QUESTION_TYPES:
        question_type = _DEFAULT_QUESTION_TYPE  # N1 deterministic fallback

    stem_polarity = data.get("stem_polarity", _DEFAULT_STEM_POLARITY)
    if stem_polarity not in _VALID_STEM_POLARITY:
        stem_polarity = _DEFAULT_STEM_POLARITY

    answer_no = _parse_answer_no(data.get("answer_no", 1), slot_id=slot.slot_id)

    return QuizItemCandidate(
        semester=spec.semester,
        course_slug=spec.course_slug,
        item_no=slot.ordinal,
        week=slot.week,
        chapter_no=spec.chapter_no,
        chapter=spec.chapter,
        section=data.get("section"),
        key_concept=data.get("key_concept"),
        question_type=question_type,
        difficulty="중",  # provisional: finalized in T030
        stem_polarity=stem_polarity,
        text=str(data.get("text", "")),
        options=options,
        answer_no=answer_no,
        option_evidence=option_evidence,
        wrong_explanation=wrong_explanation,
        leap=leap,
        textbook_evidence=None,  # filled by verify/groundedness (T028)
        answer_explanation_combined=combined,
        option_length_ok=_check_option_lengths(options),
        explanation_length_ok=_check_explanation_lengths(wrong_explanation, leap.text),
        duplicate_flag=False,
        review_note="",
        adoption_status="생성",
        note=None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_response(raw_text: str, slot_id: str) -> dict[str, Any]:
    """Parse the LLM's raw_text as a JSON object.

    Strips any markdown code fences (```json ... ```) the LLM may add.

    Args:
        raw_text: Raw string from the LLM response.
        slot_id: Slot identifier for error messages.

    Returns:
        Parsed dict matching the expected structured-response schema.

    Raises:
        ValueError: If the response is not valid JSON or is not a JSON object.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"generate_quiz_item: LLM response for slot '{slot_id}' is not valid "
            f"JSON. Error: {exc}. Raw text (first 200 chars): {raw_text[:200]!r}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"generate_quiz_item: LLM response for slot '{slot_id}' parsed as "
            f"{type(data).__name__}, expected a JSON object."
        )
    return data


def _parse_answer_no(value: object, slot_id: str) -> int:
    """Coerce an LLM-provided answer_no to int, failing loud on bad values.

    Args:
        value: The raw ``answer_no`` value from the parsed response.
        slot_id: Slot identifier for the error message.

    Returns:
        The integer answer number (range validity enforced by QuizItemCandidate).

    Raises:
        ValueError: If ``value`` is ``None`` or not coercible to int.
    """
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"generate_quiz_item: slot '{slot_id}' has a malformed 'answer_no' "
            f"value {value!r} (expected an integer 1-5)."
        ) from exc


def _normalize_option_evidence(
    raw: object,
    options: list[str],
) -> list[str]:
    """Return a 5-element option-evidence list, padding with placeholders.

    The schema requires ``len(option_evidence) == 5``.  When the LLM omits or
    under-fills the field, missing entries are filled with a deterministic
    placeholder so construction never fails (groundedness is verified later).

    Args:
        raw: The raw ``option_evidence`` value from the response.
        options: The parsed options (used only for length alignment).

    Returns:
        A list of exactly ``len(options)`` evidence strings (5 in the valid case).
    """
    target = len(options)
    items = [str(x) for x in raw] if isinstance(raw, list) else []
    if len(items) >= target:
        return items[:target] if target else items
    return items + [MISSING_EVIDENCE_PLACEHOLDER] * (target - len(items))


def _check_option_lengths(options: list[str]) -> bool:
    """Return True iff every option is 30–50 chars (incl. spaces).

    Args:
        options: The parsed option strings.

    Returns:
        ``True`` iff ``options`` is non-empty and each option's codepoint length
        is within ``[30, 50]``.
    """
    if not options:
        return False
    return all(_OPTION_MIN_LEN <= len(o) <= _OPTION_MAX_LEN for o in options)


def _check_explanation_lengths(wrong_explanation: str, leap_text: str) -> bool:
    """Return True iff wrong_explanation and leap_text are each <=200 chars.

    Args:
        wrong_explanation: The wrong-answer explanation.
        leap_text: The leap explanation body.

    Returns:
        ``True`` iff both strings are at most ``200`` codepoints (incl. spaces).
    """
    return len(wrong_explanation) <= _EXPLANATION_MAX_LEN and len(leap_text) <= _EXPLANATION_MAX_LEN


__all__ = ["MISSING_EVIDENCE_PLACEHOLDER", "generate_quiz_item"]
