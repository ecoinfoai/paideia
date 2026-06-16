"""T044 — Formative candidate generation via LLM backend (US3).

``generate_formative_item`` runs the per-slot formative-generation flow,
analogous to :func:`~maieutica.generate.quiz_gen.generate_quiz_item` but for
short-answer formative items:

1. Build the formative generation bundle (the analogue of
   :func:`~maieutica.generate.bundle.build_bundle`, rendering
   ``templates/prompt_formative.txt``).
2. Call ``cache.generate(request)`` — the cache guarantees byte-identical
   re-runs; the backend is only invoked on a cache miss.
3. Parse the LLM's structured JSON response and assemble a COMPLETE,
   schema-valid :class:`~paideia_shared.schemas.FormativeItemCandidate`.

Staged-enrichment contract
--------------------------
``FormativeItemCandidate`` is ``frozen=True``.  This function builds a fully
valid candidate with ``textbook_evidence=None``; it is grounded later by
:func:`~maieutica.verify.groundedness.ground_formative` via ``model_copy``.

``support_high`` is the leap/도약 axis (FR-014): it bridges high-achievers to
the next concept, mirroring the quiz ``leap``.

Expected LLM response shape (JSON, UTF-8)::

    {
      "no":           1,
      "chapter_no":   8,
      "topic":        "개념이해",
      "question":     "...",
      "limit":        "200자 내외",
      "model_answer": "...",
      "purpose":      "...",
      "keywords":     ["...", "...", "..."],
      "rubric_high":  "...",
      "rubric_mid":   "...",
      "rubric_low":   "...",
      "support_high": "...",
      "support_mid":  "...",
      "support_low":  "..."
    }

Usage::

    from maieutica.generate.formative_gen import generate_formative_item

    item = generate_formative_item(slot, spec, chunks, cache)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from paideia_shared.schemas import (
    FormativeItemCandidate,
    MaieuticaGenerationSpec,
    TextbookChunk,
)

from maieutica.generate.backend import GenerationRequest, InputHashCache
from maieutica.plan.slots import Slot

# templates/ lives at modules/maieutica/templates, two parents above the
# src/maieutica package root (src/maieutica/generate/formative_gen.py → maieutica).
_TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "templates" / "prompt_formative.txt"

# Default topic hint when the planner has not assigned one.  The LLM re-emits
# its own topic, parsed below; this only seeds the prompt deterministically.
_DEFAULT_TOPIC = "개념이해"


@lru_cache(maxsize=1)
def _load_template() -> str:
    """Load and cache the formative prompt template, stripping comment lines.

    Leading ``#`` comment lines (documentation of placeholders) are removed so
    they never reach the LLM.  The remainder is returned verbatim for
    ``str.format`` rendering.

    Returns:
        The template body with comment lines stripped.

    Raises:
        FileNotFoundError: If the template file is missing (boundary failure).
    """
    raw = _TEMPLATE_PATH.read_text(encoding="utf-8")
    body_lines = [line for line in raw.splitlines() if not line.startswith("#")]
    return "\n".join(body_lines).lstrip("\n")


def _select_chunks(
    slot: Slot,
    chunks: list[TextbookChunk],
) -> list[TextbookChunk]:
    """Return chunks matching the slot's chapter, sorted deterministically.

    Args:
        slot: The formative slot whose chapter we need.
        chunks: All available TextbookChunk objects (may span many chapters).

    Returns:
        Chunks with ``chapter_no == slot.chapter_no`` sorted by
        ``(chapter_no, line_start, chunk_id)`` for stable ordering.
    """
    matching = [c for c in chunks if c.chapter_no == slot.chapter_no]
    return sorted(matching, key=lambda c: (c.chapter_no, c.line_start, c.chunk_id))


def _derive_section(chunks: list[TextbookChunk]) -> str:
    """Derive a section label from the (already sorted) chapter chunks.

    Args:
        chunks: Chapter-matched chunks in stable order.

    Returns:
        The first chunk's section, or ``"(전체)"`` if none carry a section.
    """
    for c in chunks:
        if c.section:
            return c.section
    return "(전체)"


def build_formative_bundle(
    slot: Slot,
    spec: MaieuticaGenerationSpec,
    chunks: list[TextbookChunk],
) -> GenerationRequest:
    """Build a deterministic GenerationRequest for one formative slot.

    Mirrors :func:`~maieutica.generate.bundle.build_bundle` but renders the
    formative prompt template.  Output is byte-identical for identical
    ``(slot, spec, chunks)`` input.

    Args:
        slot: The planned formative slot.
        spec: The generation specification (chapter / semester / course labels).
        chunks: All available TextbookChunk objects (filtered internally).

    Returns:
        A ``GenerationRequest`` ready for ``cache.generate(request)``.
    """
    selected = _select_chunks(slot, chunks)

    textbook_context = "\n\n".join(c.text for c in selected) if selected else "(교재 본문 없음)"
    section = _derive_section(selected)
    key_concept = spec.chapter

    prompt = _load_template().format(
        chapter=spec.chapter,
        chapter_no=spec.chapter_no,
        section=section,
        week=spec.week,
        formative_count=1,
        textbook_context=textbook_context,
        key_concept=key_concept,
        slot_id=slot.slot_id,
        topic=_DEFAULT_TOPIC,
    )

    context_refs = [f"{c.source_file}#{c.chunk_id}" for c in selected]

    metadata: dict[str, object] = {
        "slot_id": slot.slot_id,
        "kind": slot.kind,
        "week": spec.week,
        "chapter": spec.chapter,
        "chapter_no": spec.chapter_no,
        "section": section,
        "chunk_ids": [c.chunk_id for c in selected],
    }

    return GenerationRequest(
        slot_id=slot.slot_id,
        prompt=prompt,
        context_refs=context_refs,
        metadata=metadata,
    )


def generate_formative_item(
    slot: Slot,
    spec: MaieuticaGenerationSpec,
    chunks: list[TextbookChunk],
    cache: InputHashCache,
) -> FormativeItemCandidate:
    """Generate one formative candidate for a slot via the LLM backend.

    Args:
        slot: The planned formative slot.
        spec: The generation specification (identity / chapter labels).
        chunks: All available TextbookChunk objects (filtered by the bundle).
        cache: InputHashCache wrapping the backend (invoked on a cache miss).

    Returns:
        A complete, schema-valid
        :class:`~paideia_shared.schemas.FormativeItemCandidate` with
        ``textbook_evidence=None`` (grounded later by ``ground_formative``).

    Raises:
        ValueError: If the LLM response is not valid JSON, is not a JSON object,
            or carries a malformed required field.
    """
    request = build_formative_bundle(slot, spec, chunks)
    response = cache.generate(request)
    data = _parse_response(response.raw_text, slot_id=slot.slot_id)

    return FormativeItemCandidate(
        semester=spec.semester,
        course_slug=spec.course_slug,
        no=_parse_no(data.get("no", slot.ordinal), slot_id=slot.slot_id),
        chapter_no=spec.chapter_no,
        topic=str(data.get("topic", _DEFAULT_TOPIC)),
        question=str(data.get("question", "")),
        limit=str(data.get("limit", "200자 내외")),
        model_answer=str(data.get("model_answer", "")),
        purpose=str(data.get("purpose", "")),
        keywords=_parse_keywords(data.get("keywords")),
        rubric_high=str(data.get("rubric_high", "")),
        rubric_mid=str(data.get("rubric_mid", "")),
        rubric_low=str(data.get("rubric_low", "")),
        support_high=str(data.get("support_high", "")),  # leap axis (FR-014)
        support_mid=str(data.get("support_mid", "")),
        support_low=str(data.get("support_low", "")),
        textbook_evidence=None,  # grounded by verify/groundedness (ground_formative)
        review_note="",
        adoption_status="생성",
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
            f"generate_formative_item: LLM response for slot '{slot_id}' is not "
            f"valid JSON. Error: {exc}. Raw text (first 200 chars): {raw_text[:200]!r}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"generate_formative_item: LLM response for slot '{slot_id}' parsed as "
            f"{type(data).__name__}, expected a JSON object."
        )
    return data


def _parse_no(value: object, slot_id: str) -> int:
    """Coerce an LLM-provided ``no`` to int, failing loud on bad values.

    Args:
        value: The raw ``no`` value from the parsed response.
        slot_id: Slot identifier for the error message.

    Returns:
        The integer item number (range validity enforced by the schema).

    Raises:
        ValueError: If ``value`` is ``None`` or not coercible to int.
    """
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"generate_formative_item: slot '{slot_id}' has a malformed 'no' "
            f"value {value!r} (expected a positive integer)."
        ) from exc


def _parse_keywords(raw: object) -> list[str]:
    """Return a list of keyword strings from the raw response value.

    Args:
        raw: The raw ``keywords`` value from the response (expected a list).

    Returns:
        A list of stringified keywords; an empty list when ``raw`` is not a list.
    """
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


__all__ = ["build_formative_bundle", "generate_formative_item"]
