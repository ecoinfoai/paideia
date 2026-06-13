"""Unit tests for Slot subsection-assignment fields — T006.

TDD: failing tests written BEFORE implementation (RED → GREEN).

Covers the three subsection-assignment fields added to the frozen ``Slot``
dataclass (data-model.md §1):
- ``subsection_chunk_id: str`` — default ``""`` (sentinel "unassigned").
- ``subsection_section: str | None`` — default ``None``.
- ``intra_ordinal: int`` — default ``0`` (sentinel "unassigned").

The defaults must keep the existing ``plan_slots`` construction (which omits
these fields) non-destructive, and the dataclass must stay frozen.
"""

from __future__ import annotations

import dataclasses

import pytest


class TestSlotSubsectionFields:
    def test_old_construction_uses_defaults(self) -> None:
        from maieutica.plan.slots import Slot

        slot = Slot(
            slot_id="quiz-3-001",
            kind="quiz",
            week=3,
            chapter_no=8,
            ordinal=1,
        )
        assert slot.subsection_chunk_id == ""
        assert slot.subsection_section is None
        assert slot.intra_ordinal == 0

    def test_new_fields_round_trip(self) -> None:
        from maieutica.plan.slots import Slot

        slot = Slot(
            slot_id="quiz-3-001",
            kind="quiz",
            week=3,
            chapter_no=8,
            ordinal=1,
            subsection_chunk_id="chunk-08-002",
            subsection_section="8.2 가스 교환",
            intra_ordinal=2,
        )
        assert slot.subsection_chunk_id == "chunk-08-002"
        assert slot.subsection_section == "8.2 가스 교환"
        assert slot.intra_ordinal == 2

    def test_slot_is_frozen(self) -> None:
        from maieutica.plan.slots import Slot

        slot = Slot(
            slot_id="quiz-3-001",
            kind="quiz",
            week=3,
            chapter_no=8,
            ordinal=1,
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            slot.intra_ordinal = 5  # type: ignore[misc]

    def test_fields_exist_with_documented_defaults(self) -> None:
        from maieutica.plan.slots import Slot

        by_name = {f.name: f for f in dataclasses.fields(Slot)}
        assert by_name["subsection_chunk_id"].default == ""
        assert by_name["subsection_section"].default is None
        assert by_name["intra_ordinal"].default == 0
