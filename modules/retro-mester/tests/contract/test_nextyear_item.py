"""Contract tests for NextYearItemProposal (M5, T009).

RED → GREEN: written before schema; ensure valid construction and
Literal validation for proposed_kind fire correctly.
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import NextYearItemProposal
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_kwargs() -> dict:
    return {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "missing_signal": "선행학습 수준 자가보고",
        "target_unit_or_axis": "8장 호흡계통",
        "proposed_kind": "likert",
        "rationale": "해당 단원 기초구멍 가설을 확인하려면 선행지식 자기평가 문항이 필요함.",
    }


# ---------------------------------------------------------------------------
# Valid construction — all proposed_kind values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    ["likert", "single_select", "multiselect", "freetext"],
)
def test_valid_all_kinds(kind: str) -> None:
    """All four proposed_kind values are accepted."""
    kw = _valid_kwargs()
    kw["proposed_kind"] = kind
    proposal = NextYearItemProposal(**kw)
    assert proposal.proposed_kind == kind


def test_valid_construction() -> None:
    """A fully specified proposal is accepted and fields round-trip."""
    proposal = NextYearItemProposal(**_valid_kwargs())
    assert proposal.missing_signal == "선행학습 수준 자가보고"
    assert proposal.semester == "2026-1"


# ---------------------------------------------------------------------------
# Invalid proposed_kind
# ---------------------------------------------------------------------------


def test_invalid_proposed_kind() -> None:
    """A non-Literal proposed_kind raises ValidationError."""
    kw = _valid_kwargs()
    kw["proposed_kind"] = "ranking"  # not in Literal
    with pytest.raises(ValidationError):
        NextYearItemProposal(**kw)


# ---------------------------------------------------------------------------
# Extra-field rejection + frozen
# ---------------------------------------------------------------------------


def test_extra_field_rejected() -> None:
    """extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        NextYearItemProposal(**_valid_kwargs(), unknown_field="bad")


def test_frozen_prevents_mutation() -> None:
    """frozen=True prevents in-place attribute mutation."""
    proposal = NextYearItemProposal(**_valid_kwargs())
    with pytest.raises(Exception):
        proposal.proposed_kind = "freetext"  # type: ignore[misc]
