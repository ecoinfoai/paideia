"""T026 — Textbook item generation via LLM backend (US1 only).

``generate_item`` orchestrates the full per-slot generation flow for
**textbook-sourced** slots:

1. Build the generation bundle (T025 ``build_bundle``).
2. Call ``cache.generate(request)`` — the cache ensures byte-identical
   re-runs; the backend is only called on a cache miss.
3. Parse the LLM's structured JSON response into ``ExamItemDraft`` fields.
4. Anchor groundedness data: search the ``evidence_index`` for the item's
   ``key_concept`` → populate ``TextbookEvidence`` with source_file, line,
   found_text, status (``"확인"`` if found, ``"미확인"`` if not).

Non-textbook sources (``"formative"``, ``"quiz"``) raise
``NotImplementedError`` with an explicit "see US2/US3" message — those paths
are implemented in later sub-units.

Expected LLM response shape (JSON, UTF-8)::

    {
      "question_type": "지식축적" | "맥락통찰",
      "difficulty":    "1_쉬움" | "2_보통" | "3_어려움",
      "stem_polarity": "부정형" | "긍정형",
      "text":          "<발문>",
      "options":       ["<①>", "<②>", "<③>", "<④>", "<⑤>"],
      "answer_no":     1~5,
      "distractor_rationale": ["<①근거>", ..., "<⑤근거>"],
      "wrong_explanation": "<270~330자>",
      "leap_explanation":  "<270~330자>",
      "intent":        "<40~60자>",
      "key_concept":   "<1~3단어 핵심개념>"
    }

Usage::

    from examen.generate.item_gen import generate_item

    item = generate_item(
        slot=slot,
        chunks=chunks,
        evidence_index=evidence_index,
        backend=backend,
        cache=cache,
    )
"""

from __future__ import annotations

import json

from paideia_shared.schemas import ExamItemDraft, TextbookChunk, TextbookEvidence

from examen.generate.backend import InputHashCache, LLMBackend
from examen.generate.bundle import build_bundle
from examen.plan.blueprint import Slot
from examen.silver.evidence_index import EvidenceIndex

# ---------------------------------------------------------------------------
# Item generation
# ---------------------------------------------------------------------------


def generate_item(
    slot: Slot,
    chunks: list[TextbookChunk],
    evidence_index: EvidenceIndex,
    backend: LLMBackend,
    cache: InputHashCache,
) -> ExamItemDraft:
    """Generate one exam item for a textbook slot via the LLM backend.

    Args:
        slot: The planned exam slot (must have ``source == "textbook"``).
        chunks: All available TextbookChunk objects (filtered internally).
        evidence_index: Searchable index over the chapter's original lines.
        backend: LLM backend (used on cache miss only).
        cache: InputHashCache wrapping the backend.

    Returns:
        A schema-valid :class:`~paideia_shared.schemas.ExamItemDraft` with
        ``source="textbook"``, 5 options, and ``textbook_evidence`` anchored.

    Raises:
        NotImplementedError: If ``slot.source`` is ``"formative"`` (see US2)
            or ``"quiz"`` (see US3).
        ValueError: If the LLM response cannot be parsed or is structurally
            invalid.
    """
    # 출처 확인 — textbook 이외는 아직 미구현
    if slot.source == "formative":
        raise NotImplementedError(
            f"Formative-to-MCQ conversion is not implemented in US1. "
            f"See US2 (slot_id={slot.slot_id}). "
            "This path will be filled by a later sub-unit."
        )
    if slot.source == "quiz":
        raise NotImplementedError(
            f"Quiz variation generation is not implemented in US1. "
            f"See US3 (slot_id={slot.slot_id}). "
            "This path will be filled by a later sub-unit."
        )

    # Step 1: build bundle (T025)
    request = build_bundle(slot, chunks)

    # Step 2: call cache (→ backend on miss)
    response = cache.generate(request)

    # Step 3: parse structured JSON
    item_data = _parse_response(response.raw_text, slot_id=slot.slot_id)

    # Step 4: anchor groundedness evidence
    key_concept: str | None = item_data.get("key_concept")
    textbook_evidence = _anchor_evidence(
        key_concept=key_concept,
        evidence_index=evidence_index,
    )

    # Step 5: assemble ExamItemDraft
    # difficulty는 슬롯에서 강제 (LLM 응답 무시) — 결정론 보장
    difficulty = slot.difficulty

    # question_type: LLM 응답 사용, 기본값 "지식축적"
    question_type = item_data.get("question_type", "지식축적")
    if question_type not in ("지식축적", "맥락통찰"):
        question_type = "지식축적"

    # stem_polarity: LLM 응답 사용, 기본값 "부정형"
    stem_polarity = item_data.get("stem_polarity", "부정형")
    if stem_polarity not in ("부정형", "긍정형"):
        stem_polarity = "부정형"

    # item_no: slot_id 에서 추출 (예: "slot-001" → 1)
    item_no = _extract_item_no(slot.slot_id)

    # 옵션 길이 검증 (safe default — verify 단계에서 재계산)
    options = item_data.get("options", [])
    option_length_ok = _check_option_lengths(options)

    return ExamItemDraft(
        semester=_infer_semester(chunks),
        course_slug=_infer_course_slug(chunks),
        item_no=item_no,
        source="textbook",
        source_ref=None,
        chapter=slot.chapter,
        chapter_no=slot.chapter_no,
        section=slot.section,
        week=None,
        key_concept=key_concept,
        is_emphasized=None,
        emphasis_class_count=None,
        question_type=question_type,
        bloom=None,
        difficulty=difficulty,
        stem_polarity=stem_polarity,
        text=item_data.get("text", ""),
        options=options,
        answer_no=int(item_data.get("answer_no", 1)),
        distractor_rationale=item_data.get("distractor_rationale", []),
        wrong_explanation=item_data.get("wrong_explanation", ""),
        leap_explanation=item_data.get("leap_explanation", ""),
        textbook_evidence=textbook_evidence,
        intent=item_data.get("intent", ""),
        option_length_ok=option_length_ok,
        duplicate_flag=False,
        review_note="",
        adoption_status="생성",
        note=None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_response(raw_text: str, slot_id: str) -> dict:  # type: ignore[type-arg]
    """Parse the LLM's raw_text as JSON, returning the item dict.

    Strips any markdown code fences (```json ... ```) that the LLM may add.

    Args:
        raw_text: Raw string from the LLM response.
        slot_id: Slot identifier for error messages.

    Returns:
        Parsed dict matching the expected structured-response schema.

    Raises:
        ValueError: If the response is not valid JSON.
    """
    text = raw_text.strip()
    # markdown 코드 펜스 제거
    if text.startswith("```"):
        lines = text.splitlines()
        # 첫 줄 (```json 또는 ```) 제거, 마지막 줄 (```) 제거
        inner = lines[1:] if lines[-1].strip() == "```" else lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"generate_item: LLM response for slot '{slot_id}' is not valid JSON. "
            f"Error: {exc}. Raw text (first 200 chars): {raw_text[:200]!r}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"generate_item: LLM response for slot '{slot_id}' parsed as "
            f"{type(data).__name__}, expected dict."
        )
    return data


def _anchor_evidence(
    key_concept: str | None,
    evidence_index: EvidenceIndex,
) -> TextbookEvidence:
    """Search evidence_index for key_concept; return a TextbookEvidence anchor.

    Args:
        key_concept: The item's key concept keyword from the LLM response.
            May be ``None``.
        evidence_index: Searchable index over the original textbook lines.

    Returns:
        TextbookEvidence with status ``"확인"`` if at least one hit is found,
        ``"미확인"`` otherwise.
    """
    if not key_concept:
        return TextbookEvidence(
            source_file=evidence_index.source_file,
            line=None,
            found_text=None,
            status="미확인",
            search_term=None,
        )

    hits = evidence_index.search(key_concept)
    if hits:
        first = hits[0]
        return TextbookEvidence(
            source_file=evidence_index.source_file,
            line=first.line_no,
            found_text=first.found_text,
            status="확인",
            search_term=key_concept,
        )

    return TextbookEvidence(
        source_file=evidence_index.source_file,
        line=None,
        found_text=None,
        status="미확인",
        search_term=key_concept,
    )


def _extract_item_no(slot_id: str) -> int:
    """Extract a positive integer item_no from a slot_id string.

    Handles the ``"slot-NNN"`` pattern; falls back to 1 for unknown formats.

    Args:
        slot_id: Slot identifier string.

    Returns:
        Positive integer item_no.
    """
    # "slot-001" → 1, "slot-042" → 42
    parts = slot_id.rsplit("-", 1)
    if len(parts) == 2:
        try:
            return max(1, int(parts[1]))
        except ValueError:
            pass
    return 1


def _infer_semester(chunks: list[TextbookChunk]) -> str:
    """Infer semester from chunks (first chunk wins).

    Args:
        chunks: List of TextbookChunk objects.

    Returns:
        Semester code string, or ``"unknown"`` if no chunks available.
    """
    return chunks[0].semester if chunks else "unknown"


def _infer_course_slug(chunks: list[TextbookChunk]) -> str:
    """Infer course_slug from chunks (first chunk wins).

    Args:
        chunks: List of TextbookChunk objects.

    Returns:
        CourseSlug string, or ``"unknown"`` if no chunks available.
    """
    return chunks[0].course_slug if chunks else "unknown"


def _check_option_lengths(options: list[str]) -> bool:
    """Check that all options are 30–40 codepoints (번호 포함).

    Args:
        options: List of option strings (exactly 5 expected).

    Returns:
        ``True`` iff all options satisfy 30 ≤ len ≤ 40.
    """
    if not options:
        return False
    return all(30 <= len(opt) <= 40 for opt in options)


__all__ = ["generate_item"]
