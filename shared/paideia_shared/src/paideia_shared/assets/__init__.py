"""Static asset schemas + bundled YAML resources for paideia modules.

Distinct from ``paideia_shared.schemas`` (which holds Bronze/Silver/Gold data
contracts): this subpackage holds the Pydantic schema for *operator-facing
assets* — manual text, etc — plus the YAML resources themselves.
"""

from .manual_text import (
    ManualAxisEntry,
    ManualGroupEntry,
    ManualMetadata,
    ManualSection,
    ManualTextAsset,
)

__all__ = [
    "ManualAxisEntry",
    "ManualGroupEntry",
    "ManualMetadata",
    "ManualSection",
    "ManualTextAsset",
]
