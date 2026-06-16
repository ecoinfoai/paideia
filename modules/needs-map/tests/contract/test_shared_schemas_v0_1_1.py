"""Contract tests for v0.1.1 shared schema deltas (T019).

Covers Foundation 2B–2D + 2E delta surface:
- StandardAxisKey 8-key Literal (T007)
- AuxiliaryGroupKey + FreetextAreaKey Literals (T007)
- STANDARD_AXIS_KEYS tuple (T008)
- MappingColumn.kind Literal expanded to 5 values incl. single_select (T009)
- MappingColumn rejects aggregate='mean' on non-likert kinds (T010 rule
  surfaced through MappingColumn validator per data-model §2 / FR-011)
- DiagnosticMappingConfig V6 enforces required = 8-key set exactly (T010)
- FactorScoreRow has 24 axis fields (8 axes × 3 — T011)
- FactorScoresLongRow.student_id rejects non-10-digit (T013)
- AxisSummaryRow rejects mismatched per-row_kind fields (T014)
- FreetextAuditRow requires both model and tokenizer hashes (T015)
- ManualTextAsset Pydantic schema validates baseline structure (T016)

These tests are designed to FAIL on the v0.1.0 schema baseline and PASS
once T007–T017 land. They do not exercise the runtime pipeline.

Spec: specs/003-needs-map-v0-1-1/data-model.md (§1–§9 + manual asset)
      specs/003-needs-map-v0-1-1/tasks.md T019.
"""

from __future__ import annotations

import typing

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# T007 + T008 — StandardAxisKey + AuxiliaryGroupKey + FreetextAreaKey
# ---------------------------------------------------------------------------


def test_standard_axis_key_has_exactly_eight_keys() -> None:
    """``StandardAxisKey`` Literal MUST contain the 8 v1.1.0 vocabulary keys."""
    from paideia_shared.schemas import StandardAxisKey

    members = set(typing.get_args(StandardAxisKey))
    expected = {
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    }
    assert members == expected, (
        f"StandardAxisKey delta from constitution v1.1.0: "
        f"missing={expected - members}, extra={members - expected}"
    )


def test_standard_axis_keys_constant_mirrors_literal() -> None:
    """``STANDARD_AXIS_KEYS`` tuple MUST mirror the Literal exactly."""
    from paideia_shared.schemas._common import STANDARD_AXIS_KEYS, StandardAxisKey

    assert isinstance(STANDARD_AXIS_KEYS, tuple)
    assert set(STANDARD_AXIS_KEYS) == set(typing.get_args(StandardAxisKey))
    assert len(STANDARD_AXIS_KEYS) == 8


def test_auxiliary_group_key_has_three_keys() -> None:
    """``AuxiliaryGroupKey`` Literal MUST contain the 3 v0.1.1 group keys."""
    from paideia_shared.schemas._common import AuxiliaryGroupKey

    members = set(typing.get_args(AuxiliaryGroupKey))
    assert members == {"prior_readiness", "interest_topics", "categorical_intent"}


def test_freetext_area_key_has_two_keys() -> None:
    """``FreetextAreaKey`` Literal MUST contain the 2 freetext source keys."""
    from paideia_shared.schemas._common import FreetextAreaKey

    members = set(typing.get_args(FreetextAreaKey))
    assert members == {"anxiety_freetext", "experience_freetext"}


# ---------------------------------------------------------------------------
# T009 + T010 — MappingColumn.kind 5 values + per-kind rules
# ---------------------------------------------------------------------------


def test_mapping_column_kind_accepts_five_values() -> None:
    """``MappingColumn.kind`` MUST accept all 5 v0.1.1 values."""
    from paideia_shared.schemas import MappingColumn

    kind_field = MappingColumn.model_fields["kind"]
    accepted = set(typing.get_args(kind_field.annotation))
    assert accepted == {
        "identity",
        "likert",
        "single_select",
        "multiselect",
        "freetext",
    }


def test_mapping_column_rejects_aggregate_mean_on_single_select() -> None:
    """FR-011: aggregate='mean' MUST be rejected on kind='single_select'."""
    from paideia_shared.schemas import MappingColumn

    with pytest.raises(ValidationError) as exc:
        MappingColumn(
            source="q5",
            kind="single_select",
            axis="prior_readiness",
            aggregate="mean",
        )
    assert "aggregate" in str(exc.value).lower() or "mean" in str(exc.value).lower()


def test_mapping_column_rejects_aggregate_mean_on_multiselect() -> None:
    """FR-011: aggregate='mean' MUST be rejected on kind='multiselect'."""
    from paideia_shared.schemas import MappingColumn

    with pytest.raises(ValidationError):
        MappingColumn(
            source="q11",
            kind="multiselect",
            axis="interest_topics",
            aggregate="mean",
        )


def test_mapping_column_likert_with_quant_axis_ok() -> None:
    """kind='likert' with a quantitative axis MUST validate."""
    from paideia_shared.schemas import MappingColumn

    column = MappingColumn(
        source="q1",
        kind="likert",
        axis="motivation",
        aggregate="mean",
    )
    assert column.kind == "likert"


def test_mapping_column_optional_ordinal_map_field_present() -> None:
    """data-model.md §2: MappingColumn MUST expose optional ``ordinal_map``."""
    from paideia_shared.schemas import MappingColumn

    assert "ordinal_map" in MappingColumn.model_fields, (
        "MappingColumn is missing the v0.1.1 ordinal_map field"
    )
    column = MappingColumn(
        source="q1",
        kind="likert",
        axis="motivation",
        aggregate="mean",
        ordinal_map={"전혀 그렇지 않다": 1, "매우 그렇다": 7},
    )
    assert column.ordinal_map == {"전혀 그렇지 않다": 1, "매우 그렇다": 7}


# ---------------------------------------------------------------------------
# T010 — DiagnosticMappingConfig V6 with 8-key axes.required strict
# ---------------------------------------------------------------------------


def _eight_axis_columns() -> list[dict[str, typing.Any]]:
    """Helper: minimal 1-likert-column-per-axis fixture for V6 validator."""
    return [
        {"source": "q_id", "kind": "identity", "axis": None, "aggregate": None},
    ] + [
        {
            "source": f"q_{axis}",
            "kind": "likert",
            "axis": axis,
            "aggregate": "mean",
        }
        for axis in (
            "digital_efficacy",
            "motivation",
            "time_availability",
            "material_preference",
            "study_strategy",
            "study_environment",
            "social_learning",
            "feedback_seeking",
        )
    ]


def test_diagnostic_mapping_v6_accepts_full_eight_keys() -> None:
    """V6 MUST accept axes.required = full 8-key vocabulary."""
    from paideia_shared.schemas import DiagnosticMappingConfig

    config = DiagnosticMappingConfig(
        metadata={
            "semester": "2026-1",
            "course_slug": "anatomy",
            "mapping_version": 2,
        },
        columns=_eight_axis_columns(),
        axes={
            "required": [
                "digital_efficacy",
                "motivation",
                "time_availability",
                "material_preference",
                "study_strategy",
                "study_environment",
                "social_learning",
                "feedback_seeking",
            ],
            "optional": [],
        },
    )
    assert len(config.axes.required) == 8


def test_diagnostic_mapping_v6_rejects_missing_axis() -> None:
    """V6 MUST reject axes.required with fewer than 8 keys (FR-013 strict)."""
    from paideia_shared.schemas import DiagnosticMappingConfig

    columns = _eight_axis_columns()
    # Drop one axis from required + drop the matching column to keep V3 satisfied
    incomplete_required = [
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        # 'feedback_seeking' missing intentionally
    ]
    columns_no_fb = [c for c in columns if c.get("axis") != "feedback_seeking"]
    with pytest.raises(ValidationError) as exc:
        DiagnosticMappingConfig(
            metadata={
                "semester": "2026-1",
                "course_slug": "anatomy",
                "mapping_version": 2,
            },
            columns=columns_no_fb,
            axes={"required": incomplete_required, "optional": []},
        )
    msg = str(exc.value)
    assert "feedback_seeking" in msg or "8" in msg or "exactly" in msg


# ---------------------------------------------------------------------------
# T011 — FactorScoreRow 8 axes × 3 = 24 fields
# ---------------------------------------------------------------------------


def test_factor_score_row_has_24_axis_fields() -> None:
    """``FactorScoreRow`` MUST expose 8 axes × 3 = 24 axis fields."""
    from paideia_shared.schemas import FactorScoreRow

    expected_axes = (
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    )
    field_names = set(FactorScoreRow.model_fields.keys())
    for axis in expected_axes:
        for suffix in ("", "_z", "_missing"):
            assert f"{axis}{suffix}" in field_names, (
                f"FactorScoreRow missing v0.1.1 field {axis}{suffix}"
            )


# ---------------------------------------------------------------------------
# T012 — ScaleReliabilityRow 8-key axis_key
# ---------------------------------------------------------------------------


def test_scale_reliability_row_axis_key_is_eight_keys() -> None:
    """``ScaleReliabilityRow.axis_key`` Literal MUST mirror the 8-key vocabulary."""
    from paideia_shared.schemas import ScaleReliabilityRow

    axis_field = ScaleReliabilityRow.model_fields["axis_key"]
    accepted = set(typing.get_args(axis_field.annotation))
    assert accepted == {
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    }


# ---------------------------------------------------------------------------
# T013 — FactorScoresLongRow
# ---------------------------------------------------------------------------


def _valid_long_row_payload(student_id: str = "2026194567") -> dict[str, typing.Any]:
    """Minimal payload for FactorScoresLongRow construction in tests."""
    payload: dict[str, typing.Any] = {
        "student_id": student_id,
        "semester": "2026-1",
        "course_slug": "anatomy",
        "on_roster": True,
        "section": "A",
        "responded": True,
    }
    for axis in (
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    ):
        payload[f"{axis}_raw"] = 4.0
        payload[f"{axis}_z"] = 0.0
        payload[f"{axis}_missing"] = False
    return payload


def test_factor_scores_long_row_rejects_non_ten_digit_student_id() -> None:
    """``FactorScoresLongRow.student_id`` MUST be exactly 10 digits."""
    from paideia_shared.schemas import FactorScoresLongRow

    payload = _valid_long_row_payload(student_id="123")
    with pytest.raises(ValidationError):
        FactorScoresLongRow(**payload)


def test_factor_scores_long_row_axis_consistency_validator() -> None:
    """raw=None ↔ missing=True per data-model.md §7."""
    from paideia_shared.schemas import FactorScoresLongRow

    payload = _valid_long_row_payload()
    payload["motivation_raw"] = None
    payload["motivation_z"] = None
    payload["motivation_missing"] = False  # inconsistent — should fail
    with pytest.raises(ValidationError):
        FactorScoresLongRow(**payload)


def test_factor_scores_long_row_happy_path() -> None:
    """Happy path with consistent missing flags MUST succeed."""
    from paideia_shared.schemas import FactorScoresLongRow

    row = FactorScoresLongRow(**_valid_long_row_payload())
    assert row.student_id == "2026194567"


# ---------------------------------------------------------------------------
# T014 — AxisSummaryRow row_kind discriminator
# ---------------------------------------------------------------------------


def test_axis_summary_row_quantitative_requires_quant_fields() -> None:
    """row_kind='quantitative' MUST require n + n_items + mean_raw etc."""
    from paideia_shared.schemas import AxisSummaryRow

    # missing n / n_items / mean_raw — should fail
    with pytest.raises(ValidationError):
        AxisSummaryRow(
            row_kind="quantitative",
            axis_key="motivation",
        )


def test_axis_summary_row_auxiliary_distribution_requires_dist_fields() -> None:
    """row_kind='auxiliary_distribution' MUST require source_col + option + counts."""
    from paideia_shared.schemas import AxisSummaryRow

    with pytest.raises(ValidationError):
        AxisSummaryRow(
            row_kind="auxiliary_distribution",
            axis_key="prior_readiness",
            # missing source_col, option, count, percentage, n_responded, n_cohort
        )


def test_axis_summary_row_quantitative_happy_path() -> None:
    """Properly populated quantitative row MUST validate."""
    from paideia_shared.schemas import AxisSummaryRow

    row = AxisSummaryRow(
        row_kind="quantitative",
        axis_key="motivation",
        n=180,
        n_items=8,
        mean_raw=4.2,
        std_raw=0.9,
        p25=3.6,
        p50=4.2,
        p75=4.8,
        cronbach_alpha=0.82,
        reliability_label="high",
    )
    assert row.row_kind == "quantitative"


def test_axis_summary_row_auxiliary_distribution_happy_path() -> None:
    """Properly populated auxiliary_distribution row MUST validate."""
    from paideia_shared.schemas import AxisSummaryRow

    row = AxisSummaryRow(
        row_kind="auxiliary_distribution",
        axis_key="prior_readiness",
        source_col="q5",
        option="중간 정도",
        count=42,
        percentage=23.4,
        n_responded=180,
        n_cohort=194,
    )
    assert row.row_kind == "auxiliary_distribution"


# ---------------------------------------------------------------------------
# T015 — FreetextAuditRow per-token row + model/tokenizer hashes
# ---------------------------------------------------------------------------


def test_freetext_audit_row_requires_both_hashes() -> None:
    """FreetextAuditRow MUST require both model_sha256 and tokenizer_vocab_sha256."""
    from paideia_shared.schemas import FreetextAuditRow

    base = {
        "student_id": "2026194567",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "freetext_source": "q61_anxiety",
        "redacted_text_sha256": "a" * 64,
        "redacted_text_length": 12,
        "token_index": 0,
        "token_text": "수업",
        "token_id": 12345,
        "char_start": 0,
        "char_end": 2,
        "model_id": "searle-j/kote_for_easygoing_people",
    }
    # Missing both hash fields → must reject
    with pytest.raises(ValidationError):
        FreetextAuditRow(**base)


def test_freetext_audit_row_happy_path() -> None:
    """Fully populated row MUST validate."""
    from paideia_shared.schemas import FreetextAuditRow

    row = FreetextAuditRow(
        student_id="2026194567",
        semester="2026-1",
        course_slug="anatomy",
        freetext_source="q61_anxiety",
        redacted_text_sha256="a" * 64,
        redacted_text_length=12,
        token_index=0,
        token_text="수업",
        token_id=12345,
        char_start=0,
        char_end=2,
        model_id="searle-j/kote_for_easygoing_people",
        model_sha256="b" * 64,
        tokenizer_vocab_sha256="c" * 64,
    )
    assert row.token_index == 0


# ---------------------------------------------------------------------------
# T016 — ManualTextAsset asset schema
# ---------------------------------------------------------------------------


def test_manual_text_asset_baseline_structure() -> None:
    """``ManualTextAsset`` MUST validate the minimum 2-section structure."""
    from paideia_shared.assets.manual_text import ManualTextAsset

    asset = ManualTextAsset(
        metadata={
            "language": "ko",
            "schema_version": "1.0.0",
            "last_updated": "2026-04-28",
        },
        sections=[
            {
                "id": "introduction",
                "title": "모듈 소개",
                "body_paragraphs": ["needs-map은 사전진단 분석 모듈이다."],
            },
            {
                "id": "eight_axes",
                "title": "8 정량 축 해석 가이드",
                "body_paragraphs": [],
                "axis_entries": [
                    {
                        "key": "motivation",
                        "name_kr": "학습동기",
                        "meaning": "학습 의지·전문직 동기",
                        "example_items": ["학습 의지"],
                        "operating_use": "면담 우선순위",
                    }
                ],
            },
        ],
    )
    assert asset.metadata.language == "ko"
    assert len(asset.sections) == 2


# ---------------------------------------------------------------------------
# T017 — NeedsMapManifest schema_version 1.1.0 + new sub-models
# ---------------------------------------------------------------------------


def test_manifest_schema_version_default_is_v1_1_0() -> None:
    """v0.1.1 manifest MUST default schema_version to '1.1.0'."""
    from paideia_shared.schemas import NeedsMapManifest

    schema_version_field = NeedsMapManifest.model_fields["schema_version"]
    assert schema_version_field.default == "1.1.0"


def test_manifest_exposes_new_sub_models() -> None:
    """NeedsMapManifest MUST expose font_resolution / sentiment / new_outputs / vocabulary."""
    from paideia_shared.schemas import NeedsMapManifest

    field_names = set(NeedsMapManifest.model_fields.keys())
    assert "font_resolution" in field_names
    assert "sentiment" in field_names
    assert "new_outputs" in field_names
    assert "vocabulary" in field_names
