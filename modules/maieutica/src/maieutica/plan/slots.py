"""T023 — Generation spec → slot list (one chapter).

Turns a :class:`paideia_shared.schemas.MaieuticaGenerationSpec` into a flat,
deterministic list of :class:`Slot` objects: ``quiz_count`` quiz slots followed
by ``formative_count`` formative slots, all for the spec's single chapter.

Slot id conventions:
- quiz       → ``quiz-{week}-{nnn}``        (e.g. ``quiz-3-001``)
- formative  → ``formative-{chapter_no}-{nnn}`` (e.g. ``formative-8-001``)

Ordinals are 1-based and zero-padded to 3 digits.  This is the maieutica
analogue of ``examen.plan.blueprint`` but far simpler: no blueprint solver,
no chapter-even distribution — just N quiz + M formative for one chapter.

Usage::

    from maieutica.plan.slots import plan_slots

    slots = plan_slots(spec)   # list[Slot]
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import floor
from typing import Literal

from paideia_shared.schemas import MaieuticaGenerationSpec, TextbookChunk

SlotKind = Literal["quiz", "formative"]


@dataclass(frozen=True)
class Slot:
    """One planned generation slot for a single chapter.

    Attributes:
        slot_id: Deterministic identifier — ``quiz-{week}-{nnn}`` or
            ``formative-{chapter_no}-{nnn}`` (1-based, zero-padded ordinal).
        kind: ``"quiz"`` or ``"formative"``.
        week: Target week number (1-based).
        chapter_no: Target chapter number (1-based).
        ordinal: 1-based position within its kind.
        subsection_chunk_id: ``chunk_id`` of the assigned subsection
            (``TextbookChunk``). Defaults to ``""`` (sentinel "unassigned")
            so construction without it still succeeds. Populated later by
            ``assign_subsections``.
        subsection_section: The subsection's section label (used to derive
            prompt focus / key concept). Defaults to ``None``.
        intra_ordinal: 1-based ordinal within the same subsection (order in
            which the avoid-list is applied). Defaults to ``0`` (sentinel
            "unassigned").
    """

    slot_id: str
    kind: SlotKind
    week: int
    chapter_no: int
    ordinal: int
    subsection_chunk_id: str = ""
    subsection_section: str | None = None
    intra_ordinal: int = 0


def plan_slots(spec: MaieuticaGenerationSpec) -> list[Slot]:
    """Expand a generation spec into its quiz + formative slots.

    Quiz slots come first (ascending ordinal), then formative slots, so the
    ordering is fully deterministic for identical specs.

    Args:
        spec: Validated generation specification for one chapter run.

    Returns:
        A list of ``spec.quiz_count`` quiz slots followed by
        ``spec.formative_count`` formative slots.
    """
    slots: list[Slot] = [
        Slot(
            slot_id=f"quiz-{spec.week}-{ordinal:03d}",
            kind="quiz",
            week=spec.week,
            chapter_no=spec.chapter_no,
            ordinal=ordinal,
        )
        for ordinal in range(1, spec.quiz_count + 1)
    ]
    slots.extend(
        Slot(
            slot_id=f"formative-{spec.chapter_no}-{ordinal:03d}",
            kind="formative",
            week=spec.week,
            chapter_no=spec.chapter_no,
            ordinal=ordinal,
        )
        for ordinal in range(1, spec.formative_count + 1)
    )
    return slots


_SUBSECTION_CAP: int = 3
"""Max slots per subsection (FR-003/SC-002); never relaxed."""


def assign_subsections(
    slots: list[Slot], chunks: list[TextbookChunk]
) -> list[Slot]:
    """Distribute slots across textbook subsections by body length (cap ≤3).

    Deterministically assigns each slot to a subsection (``TextbookChunk``) so
    that the number of slots per subsection is proportional to that
    subsection's body character count (Hamilton / largest-remainder), capped at
    :data:`_SUBSECTION_CAP` per subsection, with surplus cascading to the next
    subsection still under cap. Implements contract ``slot_assignment.md``
    (invariants A1–A7).

    Capacity / drop semantics (A4):
        Total assigned = ``min(len(slots), 3 * len(chunks))``. The first
        ``capacity`` slots (in their given order) are enriched and returned; any
        surplus ``slots[capacity:]`` are DROPPED (not returned). The dropped
        count is the pipeline's shortfall to report elsewhere
        (``quality_report_shortfall.md``). The cap is never relaxed and no
        duplicate fills are produced. The returned list therefore has length
        ``capacity``.

    Returned ordering:
        Enriched slots are returned grouped by subsection in the A6 stable sort
        order, then by ``intra_ordinal`` (1..k) within each subsection. This is
        the order the downstream generation pipeline consumes — generating
        sequentially per subsection lets it accumulate the avoid-list in
        ``intra_ordinal`` authority order. (Note: this is NOT the input slot
        order.)

    Determinism (A6):
        Subsections are sorted by ``(char_count DESC, line_start ASC,
        chunk_id ASC)`` before allocation, so shuffling the input ``chunks``
        order yields a byte-identical result.

    Args:
        slots: Planned slots to assign, consumed in their given order.
        chunks: Candidate subsections; ``len(chunk.text)`` is the body char
            count used for proportional allocation.

    Returns:
        A NEW list of ``capacity`` enriched :class:`Slot` objects (frozen
        originals untouched), each with ``subsection_chunk_id`` /
        ``subsection_section`` / ``intra_ordinal`` filled, ordered by
        (subsection sort order, ``intra_ordinal``). Exception: when ``chunks``
        is empty there is nothing to assign, so the input ``slots`` are returned
        unchanged and UN-enriched (length ``len(slots)``).
    """
    # Boundary guard: no subsections ⇒ nothing assignable. Return the input
    # unchanged so an empty-chunk pipeline call degrades visibly rather than
    # silently dropping every slot. (The real pipeline never passes [].)
    if not chunks:
        return list(slots)

    capacity = min(len(slots), _SUBSECTION_CAP * len(chunks))
    working = slots[:capacity]

    ordered_chunks = sorted(
        chunks, key=lambda c: (-len(c.text), c.line_start, c.chunk_id)
    )

    allocation = _largest_remainder_alloc(
        capacity, [len(c.text) for c in ordered_chunks]
    )

    enriched: list[Slot] = []
    cursor = 0
    for chunk, alloc in zip(ordered_chunks, allocation, strict=True):
        for intra in range(1, alloc + 1):
            slot = working[cursor]
            enriched.append(
                replace(
                    slot,
                    subsection_chunk_id=chunk.chunk_id,
                    subsection_section=chunk.section,
                    intra_ordinal=intra,
                )
            )
            cursor += 1
    return enriched


def _largest_remainder_alloc(capacity: int, weights: list[int]) -> list[int]:
    """Allocate *capacity* units across *weights* (Hamilton), each capped at 3.

    The weights are assumed pre-sorted in the A6 subsection order so that ties
    in fractional remainder are broken by earlier (= longer / lower line_start)
    subsections winning the next unit, and overflow cascades to the next
    under-cap subsection.

    Args:
        capacity: Total units to distribute (``≤ 3 * len(weights)``).
        weights: Per-subsection body char counts, in A6 sort order.

    Returns:
        Per-subsection allocation parallel to *weights*; each ``≤ 3`` and the
        sum equals *capacity*.
    """
    n = len(weights)
    total = sum(weights)

    # Degenerate all-empty input: distribute evenly round-robin under cap so the
    # result stays deterministic (not expected with real cleaned chunks).
    if total == 0:
        alloc = [0] * n
        remaining = capacity
        idx = 0
        while remaining > 0:
            if alloc[idx] < _SUBSECTION_CAP:
                alloc[idx] += 1
                remaining -= 1
            idx = (idx + 1) % n
        return alloc

    ideals = [capacity * w / total for w in weights]
    alloc = [min(_SUBSECTION_CAP, floor(x)) for x in ideals]
    pool = capacity - sum(alloc)

    # Order the buckets once by (fractional part DESC, A6 index ASC). The pool is
    # then distributed in ROUNDS: each pass walks this order giving at most one
    # extra unit per under-cap bucket, so a bucket receives a SECOND extra unit
    # only after every under-cap bucket has had its first (standard Hamilton,
    # preserving A7 spread). When a longer bucket hits cap 3 it is skipped and
    # the unit cascades to the next-longest under-cap bucket (A3 overflow).
    order = sorted(range(n), key=lambda i: (-(ideals[i] - floor(ideals[i])), i))
    while pool > 0:
        for i in order:
            if pool == 0:
                break
            if alloc[i] >= _SUBSECTION_CAP:
                continue
            alloc[i] += 1
            pool -= 1
    return alloc


__all__ = ["Slot", "SlotKind", "assign_subsections", "plan_slots"]
