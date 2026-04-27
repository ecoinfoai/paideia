"""Contract tests for MappingColumn V5/V7/V8 + DiagnosticMappingConfig V6.

v0.1.1 deltas (T006 inline patch):
- ``StandardAxisKey`` is the 8-key v1.1.0 vocabulary; V6 strict requires
  ``axes.required`` to equal that set exactly. Tests that previously used
  the 6-key vocabulary now build with the 8-key set.
- ``MappingColumn.kind`` adds ``single_select``; auxiliary group keys
  (``prior_readiness`` / ``interest_topics`` / ``categorical_intent``) are
  used in lieu of v0.1.0 ``prior_knowledge`` for non-likert columns.
- Freetext columns must target ``FreetextAreaKey``
  (``anxiety_freetext`` / ``experience_freetext``).
- New V7 (aggregate='mean' only on likert) and V8 (ordinal_map only on
  likert) validators are exercised in the dedicated v0.1.1 contract test
  module (``modules/needs-map/tests/contract/test_shared_schemas_v0_1_1.py``);
  this file focuses on the V5/V6/V4-freetext patterns inherited from
  v0.1.0.
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import (
    DiagnosticMappingConfig,
    MappingAxes,
    MappingColumn,
    MappingMetadata,
)
from pydantic import ValidationError

# v0.1.1 — the 8 quantitative axes (constitution v1.1.0).
_ALL_AXES = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def _identity_col() -> MappingColumn:
    return MappingColumn(source="학번", kind="identity")


def _likert_col(axis: str = "motivation", partition: bool = False) -> MappingColumn:
    return MappingColumn(
        source=f"Q01_{axis}",
        kind="likert",
        axis=axis,
        aggregate="mean",
        partition_axis=partition,
    )


def _multiselect_col(
    axis: str = "interest_topics", partition: bool = False
) -> MappingColumn:
    """Auxiliary group multiselect (v0.1.1 — non-scoring, no aggregate=mean)."""
    return MappingColumn(
        source=f"Q03_{axis}",
        kind="multiselect",
        axis=axis,
        partition_axis=partition,
    )


def _freetext_col(
    axis: str = "anxiety_freetext", partition: bool = False
) -> MappingColumn:
    """Freetext column targeting a FreetextAreaKey (v0.1.1)."""
    return MappingColumn(
        source=f"Q62_{axis}",
        kind="freetext",
        axis=axis,
        partition_axis=partition,
    )


def _full_eight_axis_columns() -> list[MappingColumn]:
    """One likert column per quantitative axis to satisfy V6 strict."""
    return [_identity_col()] + [_likert_col(axis) for axis in _ALL_AXES]


def _config(
    columns: list[MappingColumn],
    required: list[str],
    optional: list[str] | None = None,
) -> DiagnosticMappingConfig:
    return DiagnosticMappingConfig(
        metadata=MappingMetadata(
            semester="2026-1",
            course_slug="anatomy",
            course_name_kr="인체구조와기능",
            mapping_version=2,
        ),
        columns=columns,
        axes=MappingAxes(required=required, optional=optional or []),
    )


# --- V5: partition_axis × freetext is forbidden ---


def test_v5_partition_true_likert_ok() -> None:
    col = _likert_col(partition=True)
    assert col.partition_axis is True


def test_v5_partition_true_multiselect_ok() -> None:
    col = _multiselect_col(partition=True)
    assert col.partition_axis is True


def test_v5_partition_true_freetext_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        _freetext_col(partition=True)
    assert "V5" in str(exc.value)
    assert "freetext" in str(exc.value)


def test_v5_partition_default_false() -> None:
    assert _likert_col().partition_axis is False


# --- V6: declared axes must equal the 8-key v1.1.0 vocabulary exactly ---


def test_v6_full_eight_axes_pass() -> None:
    config = _config(
        columns=_full_eight_axis_columns(),
        required=list(_ALL_AXES),
    )
    assert set(config.axes.required) == set(_ALL_AXES)


def test_v6_non_standard_required_axis_rejected() -> None:
    """A non-vocabulary required axis triggers V6 — error mentions the axis."""
    columns = _full_eight_axis_columns() + [_likert_col("self_regulation")]
    with pytest.raises(ValidationError) as exc:
        _config(
            columns=columns,
            required=[*_ALL_AXES, "self_regulation"],
        )
    msg = str(exc.value)
    assert "V6" in msg
    assert "self_regulation" in msg
    assert "minor-version bump" in msg


def test_v6_non_standard_optional_axis_rejected() -> None:
    """V6 limits ``axes.optional`` to AuxiliaryGroupKey ∪ FreetextAreaKey.

    Add a column targeting the bogus optional axis so V3 (declared axis must
    have ≥1 backing column) does not pre-empt V6 with a different complaint.
    """
    columns = [
        *_full_eight_axis_columns(),
        # Use multiselect so V7 (mean only on likert) isn't violated either.
        MappingColumn(source="Q_meta", kind="multiselect", axis="metacognition"),
    ]
    with pytest.raises(ValidationError) as exc:
        _config(
            columns=columns,
            required=list(_ALL_AXES),
            optional=["metacognition"],
        )
    assert "V6" in str(exc.value)
    assert "metacognition" in str(exc.value)


def test_v6_existing_v1_v4_validators_still_run() -> None:
    """V6 addition must not silently bypass earlier validators.

    Build a config without any identity column → V2 (exactly one identity)
    fires before V6 even gets a chance.
    """
    with pytest.raises(ValidationError) as exc:
        _config(
            columns=[_likert_col(axis) for axis in _ALL_AXES],  # no identity
            required=list(_ALL_AXES),
        )
    assert "V2" in str(exc.value)


# --- V4: freetext kind is exempt from aggregate-consistency check ---


def test_v4_freetext_and_likert_same_axis_passes() -> None:
    """likert(aggregate=mean) + freetext(aggregate=None) are independent.

    In v0.1.1 the freetext axis must live in ``FreetextAreaKey``, not in the
    quantitative vocabulary; the V4 exemption is therefore exercised by
    co-existing axes (motivation likert + anxiety_freetext) inside the same
    config.
    """
    cfg = _config(
        columns=[
            *_full_eight_axis_columns(),
            _freetext_col("anxiety_freetext"),
        ],
        required=list(_ALL_AXES),
        optional=["anxiety_freetext"],
    )
    quant_axes = {c.axis for c in cfg.columns if c.kind == "likert"}
    freetext_axes = {c.axis for c in cfg.columns if c.kind == "freetext"}
    assert quant_axes == set(_ALL_AXES)
    assert freetext_axes == {"anxiety_freetext"}


def test_v4_two_likert_inconsistent_aggregate_still_rejected() -> None:
    """Non-freetext columns with mixed aggregate values are still V4 violations."""
    columns = [
        _identity_col(),
        MappingColumn(
            source="Q01_motivation_a",
            kind="likert",
            axis="motivation",
            aggregate="mean",
        ),
        MappingColumn(
            source="Q02_motivation_b",
            kind="likert",
            axis="motivation",
            aggregate="sum",
        ),
    ]
    # Need the remaining 7 axes too so V6 does not pre-empt V4 with a stricter
    # complaint.
    for axis in _ALL_AXES:
        if axis != "motivation":
            columns.append(_likert_col(axis))
    with pytest.raises(ValidationError) as exc:
        _config(columns=columns, required=list(_ALL_AXES))
    assert "V4" in str(exc.value)
    assert "motivation" in str(exc.value)


def test_v4_two_freetext_same_axis_passes() -> None:
    """Two freetext columns sharing one axis pass — both exempt from V4."""
    cfg = _config(
        columns=[
            *_full_eight_axis_columns(),
            MappingColumn(source="Q62_a", kind="freetext", axis="anxiety_freetext"),
            MappingColumn(source="Q62_b", kind="freetext", axis="anxiety_freetext"),
        ],
        required=list(_ALL_AXES),
        optional=["anxiety_freetext"],
    )
    freetext_axes = [c.axis for c in cfg.columns if c.kind == "freetext"]
    assert freetext_axes == ["anxiety_freetext", "anxiety_freetext"]


def test_v5_partition_axis_does_not_apply_to_freetext_under_v4_exemption() -> None:
    """V5 still rejects partition_axis=True on freetext — V4 exemption is unrelated."""
    with pytest.raises(ValidationError) as exc:
        MappingColumn(
            source="Q62_anxiety_free",
            kind="freetext",
            axis="anxiety_freetext",
            partition_axis=True,
        )
    assert "V5" in str(exc.value)
