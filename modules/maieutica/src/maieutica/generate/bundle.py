"""T026 — Per-slot deterministic quiz generation-request bundle builder.

``build_bundle`` selects the :class:`~paideia_shared.schemas.TextbookChunk`
objects that match a quiz slot's chapter, then renders the prompt template at
``modules/maieutica/templates/prompt_quiz.txt`` with the slot/spec context and
the assembled textbook text, returning a fully-specified
:class:`~maieutica.generate.backend.GenerationRequest`.

The output is byte-identical for identical ``(slot, spec, chunks)`` input
because every assembly step is deterministic: chunks are sorted by
``(chapter_no, line_start)``, context refs follow that same order, and the
prompt is rendered with ``str.format`` over a fixed template.

The maieutica :class:`~maieutica.plan.slots.Slot` carries only structural
fields (``slot_id``/``kind``/``week``/``chapter_no``/``ordinal``); the human
labels (chapter, semester, course) live on the
:class:`~paideia_shared.schemas.MaieuticaGenerationSpec`, so both are required.

Usage::

    from maieutica.generate.bundle import build_bundle

    req = build_bundle(slot, spec, chunks)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from paideia_shared.schemas import MaieuticaGenerationSpec, TextbookChunk

from maieutica.generate.backend import GenerationRequest
from maieutica.plan.slots import Slot

# Default question type when the planner has not assigned one.  The LLM re-emits
# its own value, which quiz_gen (T027) validates against the Literal; this is
# only the prompt's hint, so a deterministic default keeps the bundle stable.
_DEFAULT_QUESTION_TYPE = "지식축적"

# templates/ lives at modules/maieutica/templates, i.e. two parents above the
# src/maieutica package root (src/maieutica/generate/bundle.py → .../maieutica).
_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3] / "templates" / "prompt_quiz.txt"
)


@lru_cache(maxsize=1)
def _load_template() -> str:
    """Load and cache the quiz prompt template, stripping comment lines.

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
        slot: The quiz slot whose chapter we need.
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


def build_bundle(
    slot: Slot,
    spec: MaieuticaGenerationSpec,
    chunks: list[TextbookChunk],
) -> GenerationRequest:
    """Build a deterministic GenerationRequest for one quiz slot.

    Steps:
    1. Select chunks matching the slot's chapter and sort them deterministically.
    2. Concatenate chunk texts (double-newline separated) as the prompt context.
    3. Render the prompt template with the slot/spec fields.
    4. Build ``context_refs`` as ``"{source_file}#{chunk_id}"`` strings in the
       same stable order.
    5. Build ``metadata`` for downstream traceability.

    Args:
        slot: The planned quiz slot.
        spec: The generation specification (chapter / semester / course labels).
        chunks: All available TextbookChunk objects (filtered internally).

    Returns:
        A ``GenerationRequest`` ready for ``cache.generate(request)``.
    """
    selected = _select_chunks(slot, chunks)

    textbook_context = (
        "\n\n".join(c.text for c in selected) if selected else "(교재 본문 없음)"
    )
    section = _derive_section(selected)
    key_concept = spec.chapter

    prompt = _load_template().format(
        chapter=spec.chapter,
        chapter_no=spec.chapter_no,
        section=section,
        week=spec.week,
        textbook_context=textbook_context,
        key_concept=key_concept,
        slot_id=slot.slot_id,
        question_type=_DEFAULT_QUESTION_TYPE,
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


__all__ = ["build_bundle"]
