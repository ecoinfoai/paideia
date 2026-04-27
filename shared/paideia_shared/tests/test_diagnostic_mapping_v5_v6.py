"""Contract tests for MappingColumn V5 + DiagnosticMappingConfig V6.

Existing v1-v4 tests live elsewhere; this module covers the new validators added
for needs-map (T009 partition_axis + V5, T010 V6 standard vocabulary).
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
    axis: str = "prior_knowledge", partition: bool = False
) -> MappingColumn:
    return MappingColumn(
        source=f"Q03_{axis}",
        kind="multiselect",
        axis=axis,
        aggregate="sum",
        partition_axis=partition,
    )


def _freetext_col(axis: str = "anxiety", partition: bool = False) -> MappingColumn:
    return MappingColumn(
        source=f"Q14_{axis}_freetext",
        kind="freetext",
        axis=axis,
        partition_axis=partition,
    )


def _config(columns: list[MappingColumn], required: list[str]) -> DiagnosticMappingConfig:
    return DiagnosticMappingConfig(
        metadata=MappingMetadata(
            semester="2026-1",
            course_slug="anatomy",
            course_name_kr="인체구조와기능",
            mapping_version=1,
        ),
        columns=columns,
        axes=MappingAxes(required=required, optional=[]),
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


# --- V6: declared axes must belong to standard 6 ---


def test_v6_all_standard_axes_pass() -> None:
    config = _config(
        columns=[_identity_col(), _likert_col("motivation"), _likert_col("anxiety")],
        required=["motivation", "anxiety"],
    )
    assert config.axes.required == ["motivation", "anxiety"]


def test_v6_non_standard_required_axis_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        _config(
            columns=[_identity_col(), _likert_col("self_regulation")],
            required=["self_regulation"],
        )
    msg = str(exc.value)
    assert "V6" in msg
    assert "self_regulation" in msg
    assert "minor version bump" in msg


def test_v6_non_standard_optional_axis_rejected() -> None:
    cols = [_identity_col(), _likert_col("motivation"), _likert_col("metacognition")]
    cfg = DiagnosticMappingConfig.model_construct  # bypass would silence v6 — use full
    with pytest.raises(ValidationError) as exc:
        DiagnosticMappingConfig(
            metadata=MappingMetadata(
                semester="2026-1",
                course_slug="anatomy",
                mapping_version=1,
            ),
            columns=cols,
            axes=MappingAxes(required=["motivation"], optional=["metacognition"]),
        )
    assert "V6" in str(exc.value)
    assert "metacognition" in str(exc.value)
    _ = cfg  # silence ruff F841 — keep reference for symmetry


def test_v6_existing_v1_v4_validators_still_run() -> None:
    """V6 addition must not silently bypass earlier validators."""
    # V2: missing identity → still ValueError before V6 even fires
    with pytest.raises(ValidationError) as exc:
        DiagnosticMappingConfig(
            metadata=MappingMetadata(
                semester="2026-1", course_slug="anatomy", mapping_version=1
            ),
            columns=[_likert_col("motivation"), _likert_col("anxiety")],
            axes=MappingAxes(required=["motivation", "anxiety"]),
        )
    assert "V2" in str(exc.value)


# --- V4: freetext kind is exempt from aggregate-consistency check ---


def test_v4_freetext_and_likert_same_axis_passes() -> None:
    """likert(aggregate=mean) + freetext(aggregate=None) under one axis must NOT raise V4.

    Freetext columns carry no score aggregation (Phase D consumes raw text).
    contracts/diagnostic_mapping_extension.md explicitly documents this pattern as
    valid (e.g. Q05 anxiety likert + Q62 anxiety freetext sharing axis='anxiety').
    """
    cfg = _config(
        columns=[
            _identity_col(),
            _likert_col("anxiety"),
            _freetext_col("anxiety"),
        ],
        required=["anxiety"],
    )
    assert {c.axis for c in cfg.columns if c.kind != "identity"} == {"anxiety"}


def test_v4_two_likert_inconsistent_aggregate_still_rejected() -> None:
    """Non-freetext columns with mixed aggregate values are still V4 violations."""
    with pytest.raises(ValidationError) as exc:
        DiagnosticMappingConfig(
            metadata=MappingMetadata(
                semester="2026-1", course_slug="anatomy", mapping_version=1
            ),
            columns=[
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
            ],
            axes=MappingAxes(required=["motivation"]),
        )
    assert "V4" in str(exc.value)
    assert "motivation" in str(exc.value)


def test_v4_two_freetext_same_axis_passes() -> None:
    """Two freetext columns sharing one axis pass — both exempt from V4."""
    cfg = _config(
        columns=[
            _identity_col(),
            _likert_col("anxiety"),  # anchor scoring column
            MappingColumn(source="Q62_a", kind="freetext", axis="anxiety"),
            MappingColumn(source="Q62_b", kind="freetext", axis="anxiety"),
        ],
        required=["anxiety"],
    )
    freetext_axes = [c.axis for c in cfg.columns if c.kind == "freetext"]
    assert freetext_axes == ["anxiety", "anxiety"]


def test_v5_partition_axis_does_not_apply_to_freetext_under_v4_exemption() -> None:
    """V5 still rejects partition_axis=True on freetext — V4 exemption is unrelated."""
    with pytest.raises(ValidationError) as exc:
        MappingColumn(
            source="Q62_anxiety_free",
            kind="freetext",
            axis="anxiety",
            partition_axis=True,
        )
    assert "V5" in str(exc.value)
