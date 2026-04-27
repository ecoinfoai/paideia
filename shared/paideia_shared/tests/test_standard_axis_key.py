"""Contract tests for StandardAxisKey Literal (M1, FR-AXIS-001)."""

from __future__ import annotations

import typing

import pytest
from paideia_shared.schemas import StandardAxisKey
from pydantic import BaseModel, ValidationError


class _AxisHolder(BaseModel):
    axis: StandardAxisKey


def test_standard_axis_key_has_exactly_eight_members() -> None:
    members = typing.get_args(StandardAxisKey)
    assert set(members) == {
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    }


@pytest.mark.parametrize("axis", typing.get_args(StandardAxisKey))
def test_each_standard_axis_validates(axis: str) -> None:
    holder = _AxisHolder(axis=axis)  # type: ignore[arg-type]
    assert holder.axis == axis


@pytest.mark.parametrize(
    "bad_axis",
    ["self_regulation", "Motivation", "", "study_skill", "metacognition"],
)
def test_non_standard_axis_rejected(bad_axis: str) -> None:
    with pytest.raises(ValidationError):
        _AxisHolder(axis=bad_axis)  # type: ignore[arg-type]
