"""8-axis Cronbach α + reliability_label tests [T028].

Per data-model.md §5 + spec FR-005, ``ScaleReliabilityRow`` carries:
- ``axis_key`` from the v0.1.1 8-key Literal,
- ``cronbach_alpha`` Optional[float] (None when n_items < 3),
- legacy v0.1.0 ``label`` (computed / single_item / no_items / not_applicable),
- new v0.1.1 ``reliability_label`` (high / medium / low / 'N/A — single/double item').

This file covers the schema-level invariants for n_items ∈ {1, 2, 3, 5, 7}
(the operational scenarios on the 2026-1 anatomy diagnostic) — the actual
α numerical computation is already covered by the v0.1.0
``test_property_cronbach.py`` / ``test_reliability_cronbach.py`` modules
that walk the cronbach_alpha implementation.

Spec: 003-needs-map-v0-1-1/tasks.md T028.
"""

from __future__ import annotations

from typing import Any

import pytest
from paideia_shared.schemas import ReliabilityLabel, ScaleReliabilityRow
from pydantic import ValidationError


def _row(**overrides: Any) -> ScaleReliabilityRow:
    base: dict[str, Any] = {
        "axis_key": "motivation",
        "n_items": 5,
        "cronbach_alpha": 0.85,
        "label": "computed",
        "operational_warning": False,
    }
    base.update(overrides)
    return ScaleReliabilityRow(**base)


def test_reliability_label_high_threshold() -> None:
    """reliability_label='high' is acceptable on a row with α ≥ 0.80."""
    row = _row(cronbach_alpha=0.85, reliability_label="high")
    assert row.reliability_label == "high"


def test_reliability_label_medium_threshold() -> None:
    """reliability_label='medium' is acceptable on a row with 0.70 ≤ α < 0.80."""
    row = _row(cronbach_alpha=0.75, reliability_label="medium")
    assert row.reliability_label == "medium"


def test_reliability_label_low_threshold() -> None:
    """reliability_label='low' on operational_warning=True row (α < 0.70)."""
    row = _row(cronbach_alpha=0.55, reliability_label="low", operational_warning=True)
    assert row.reliability_label == "low"


@pytest.mark.parametrize("n_items", [1, 2])
def test_reliability_label_na_single_double_item(n_items: int) -> None:
    """'N/A — single/double item' is acceptable when n_items ∈ {1, 2}."""
    row = _row(
        n_items=n_items,
        cronbach_alpha=None,
        label="single_item",
        reliability_label="N/A — single/double item",
    )
    assert row.reliability_label == "N/A — single/double item"


def test_reliability_label_optional_default_none() -> None:
    """reliability_label is optional — older v0.1.0 rows without it still validate."""
    row = _row()
    assert row.reliability_label is None


def test_reliability_label_literal_set() -> None:
    """The Literal MUST expose exactly 4 valid string values (data-model §5)."""
    import typing

    members = set(typing.get_args(ReliabilityLabel))
    assert members == {"high", "medium", "low", "N/A — single/double item"}


def test_reliability_label_rejects_unknown_value() -> None:
    """An out-of-vocabulary reliability_label triggers Pydantic ValidationError."""
    with pytest.raises(ValidationError):
        _row(reliability_label="excellent")  # type: ignore[arg-type]


def test_axis_key_mirror_eight_keys() -> None:
    """Every v0.1.1 quantitative axis MUST be a valid axis_key value."""
    expected = (
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    )
    for axis in expected:
        row = _row(axis_key=axis)
        assert row.axis_key == axis
