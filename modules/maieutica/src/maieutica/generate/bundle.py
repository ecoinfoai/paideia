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

import re
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
_TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "templates" / "prompt_quiz.txt"


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


# Leading subsection numbering markers stripped to expose the bare concept term,
# e.g. "1) 코" → "코", "가) 외비강" → "외비강", "2.1 가스 교환" → "가스 교환".
_MARKER_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)+\s+|^[0-9가-힣]+[.)]\s*")

# Rendered into the prompt's {avoid_list} placeholder when no prior points exist,
# so the template always has a value and stays deterministic.
_AVOID_NONE = "(없음)"


def _select_chunks(
    slot: Slot,
    chunks: list[TextbookChunk],
) -> list[TextbookChunk]:
    """Return the slot's context chunks, sorted deterministically.

    Subsection scoping (T017): when the slot carries a non-empty
    ``subsection_chunk_id`` that resolves to a chunk in ``chunks``, ONLY that
    one assigned subsection is returned — so each slot probes a distinct slice
    of the chapter (research R7). Otherwise (UNASSIGNED slot, e.g. the dry-run
    degrade path where ``assign_subsections`` was not run) this falls back to
    the v0.1.0 behavior: every chunk of the slot's chapter.

    Args:
        slot: The quiz slot (its ``subsection_chunk_id`` / ``chapter_no``).
        chunks: All available TextbookChunk objects (may span many chapters).

    Returns:
        Either ``[assigned_subsection]`` or all chapter-matched chunks, sorted
        by ``(chapter_no, line_start, chunk_id)`` for stable ordering.
    """
    if slot.subsection_chunk_id:
        assigned = [c for c in chunks if c.chunk_id == slot.subsection_chunk_id]
        if assigned:
            return assigned
    matching = [c for c in chunks if c.chapter_no == slot.chapter_no]
    return sorted(matching, key=lambda c: (c.chapter_no, c.line_start, c.chunk_id))


def _derive_key_concept(section_label: str | None, fallback: str) -> str:
    """Derive a subsection concept term from a section label.

    Strips a leading numbering marker (``"1) "``, ``"가) "``, ``"2.1 "``) to
    expose the bare concept. Falls back to ``fallback`` (typically the chapter
    name) when the label is ``None``, empty, or reduces to nothing after the
    marker is removed.

    Args:
        section_label: The subsection's section label, or ``None``.
        fallback: Value to return when no concept can be derived.

    Returns:
        The stripped concept term, or ``fallback``.
    """
    if not section_label:
        return fallback
    concept = _MARKER_RE.sub("", section_label).strip()
    return concept or fallback


def _render_avoid_list(avoid_list: list[str]) -> str:
    """Render the avoid-list for the prompt, preserving caller order.

    Args:
        avoid_list: Prior subsection points to avoid re-asking (order kept).

    Returns:
        A newline bullet list, or :data:`_AVOID_NONE` when empty.
    """
    if not avoid_list:
        return _AVOID_NONE
    return "\n".join(f"- {point}" for point in avoid_list)


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
    avoid_list: list[str] | None = None,
) -> GenerationRequest:
    """Build a deterministic GenerationRequest for one quiz slot.

    Steps:
    1. Select the slot's context: ONLY its assigned subsection when assigned,
       else all chapter chunks (dry-run degrade fallback). See ``_select_chunks``.
    2. Concatenate chunk texts (double-newline separated) as the prompt context.
    3. Derive ``key_concept``: subsection-derived when assigned (≠ chapter name),
       else the chapter name (v0.1.0 fallback). See ``_derive_key_concept``.
    4. Render the prompt template with the slot/spec fields, the per-item
       ``focus``, and the rendered ``avoid_list``.
    5. Build ``context_refs`` as ``"{source_file}#{chunk_id}"`` strings in the
       same stable order.
    6. Build ``metadata`` for downstream traceability (now incl. the subsection
       fields + avoid_list, which therefore participate in the cache key).

    Args:
        slot: The planned quiz slot (carries the assigned subsection, if any).
        spec: The generation specification (chapter / semester / course labels).
        chunks: All available TextbookChunk objects (filtered internally).
        avoid_list: Prior subsection points the model must NOT re-ask, in the
            order they were asked. ``None`` is treated as empty. Defaulted so
            the dry-run path and ``generate_quiz_item`` (which call without it)
            keep working; the pipeline threads a real list later (T020).

    Returns:
        A ``GenerationRequest`` ready for ``cache.generate(request)``.
    """
    avoid = avoid_list if avoid_list is not None else []
    assigned = bool(slot.subsection_chunk_id) and any(
        c.chunk_id == slot.subsection_chunk_id for c in chunks
    )
    selected = _select_chunks(slot, chunks)

    textbook_context = "\n\n".join(c.text for c in selected) if selected else "(교재 본문 없음)"
    section = _derive_section(selected)

    if assigned:
        key_concept = _derive_key_concept(slot.subsection_section, spec.chapter)
        focus = slot.subsection_section or key_concept
    else:
        key_concept = spec.chapter
        focus = spec.chapter

    prompt = _load_template().format(
        chapter=spec.chapter,
        chapter_no=spec.chapter_no,
        section=section,
        week=spec.week,
        textbook_context=textbook_context,
        key_concept=key_concept,
        focus=focus,
        avoid_list=_render_avoid_list(avoid),
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
        "key_concept": key_concept,
        "subsection_chunk_id": slot.subsection_chunk_id,
        "intra_ordinal": slot.intra_ordinal,
        "avoid_list": list(avoid),
        "chunk_ids": [c.chunk_id for c in selected],
    }

    return GenerationRequest(
        slot_id=slot.slot_id,
        prompt=prompt,
        context_refs=context_refs,
        metadata=metadata,
    )


__all__ = ["build_bundle"]
