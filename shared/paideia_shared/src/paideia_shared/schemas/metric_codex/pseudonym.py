"""PseudonymMapEntry: single-row PII pseudonymization record.

One entry per student. Bijection and uniqueness of pseudonyms across the
full collection is enforced at the collection level by the pseudonymization
service — not on this individual-row model.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .._common import CanonicalStudentId

_PSEUDONYM_PATTERN = r"^S\d{3,}$"


class PseudonymMapEntry(BaseModel):
    """One student ↔ pseudonym mapping row.

    The pattern ``^S\\d{3,}$`` accepts ``S001``, ``S012``, ``S999``, ``S1000``;
    it rejects ``S1``, ``S12``, ``X001``, lowercase variants, and empty strings.

    Note:
        ``name_kr`` is stored for display / re-identification only and must
        never be forwarded to LLM boundaries. The LLM boundary guard enforces
        pseudonym-only transmission (spec 013 §S001).

    Attributes:
        student_id: 10-digit canonical student ID.
        name_kr: Korean display name; ``None`` when not yet resolved.
        pseudonym: Opaque pseudonym token passed to LLM calls.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: CanonicalStudentId
    name_kr: str | None = Field(
        default=None,
        description="Korean display name — for display/re-id only; never sent to LLM.",
    )
    pseudonym: str = Field(
        ...,
        pattern=_PSEUDONYM_PATTERN,
        description="Pseudonym token (e.g. 'S001'). Pattern: ^S\\d{3,}$.",
    )


__all__ = ["PseudonymMapEntry"]
