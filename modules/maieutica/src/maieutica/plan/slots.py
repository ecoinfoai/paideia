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

from dataclasses import dataclass
from typing import Literal

from paideia_shared.schemas import MaieuticaGenerationSpec

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
    """

    slot_id: str
    kind: SlotKind
    week: int
    chapter_no: int
    ordinal: int


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


__all__ = ["Slot", "SlotKind", "plan_slots"]
