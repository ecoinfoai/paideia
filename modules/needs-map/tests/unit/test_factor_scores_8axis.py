"""8-axis FactorScoreRow construction tests [T027].

Asserts that pipeline-side axis iteration walks the v0.1.1 8 keys (not the
v0.1.0 6 keys) and that single_select / multiselect columns targeting a
quantitative axis are rejected at mapping load time (T029 is the dedicated
load-time coverage; this file focuses on aggregation behavior).

Spec: 003-needs-map-v0-1-1/tasks.md T027.
"""

from __future__ import annotations

import typing

from paideia_shared.schemas import FactorScoreRow

_EXPECTED_AXES = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def test_pipeline_standard_axes_constant_is_eight_keys() -> None:
    """``pipeline._STANDARD_AXES`` MUST equal the 8-key vocabulary order.

    The constant drives ``standard_axes_used`` / ``standard_axes_skipped``
    in the manifest; it must mirror ``StandardAxisKey`` exactly.
    """
    from needs_map.pipeline import _STANDARD_AXES

    assert tuple(_STANDARD_AXES) == _EXPECTED_AXES


def test_axis_labels_kr_covers_all_eight_axes() -> None:
    """Korean labels for radar / cards MUST exist for all 8 quantitative axes."""
    from needs_map.pipeline import _AXIS_LABELS_KR

    for axis in _EXPECTED_AXES:
        assert axis in _AXIS_LABELS_KR
        assert _AXIS_LABELS_KR[axis], f"empty Korean label for {axis!r}"


def test_factor_score_row_validators_iterate_eight_axes() -> None:
    """Schema-level safeguard: FactorScoreRow exposes 24 axis fields (8 × 3).

    This duplicates a Phase 2 contract test on purpose — it surfaces if the
    pipeline ever mistakenly walks fewer axes than the schema knows about.
    """
    fields = set(FactorScoreRow.model_fields.keys())
    for axis in _EXPECTED_AXES:
        for suffix in ("", "_z", "_missing"):
            assert f"{axis}{suffix}" in fields


def test_factor_score_row_construction_with_8_axes() -> None:
    """Constructing FactorScoreRow with all 8 axes populated must validate."""
    payload: dict[str, typing.Any] = {
        "student_id": "2026194042",
        "on_roster": True,
        "responded": True,
        "section": "A",
    }
    for axis in _EXPECTED_AXES:
        payload[axis] = 4.5
        payload[f"{axis}_z"] = 0.0
        payload[f"{axis}_missing"] = False
    row = FactorScoreRow(**payload)
    assert row.motivation == 4.5
    assert row.feedback_seeking == 4.5
    assert row.digital_efficacy_missing is False
