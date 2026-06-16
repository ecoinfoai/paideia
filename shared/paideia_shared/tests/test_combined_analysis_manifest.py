"""TDD tests for ``CombinedAnalysisManifest`` (M7, T010).

Validators V1 (count consistency + R-10 unmatched ≥ 0) and V3 (top3 ≤ 3),
plus field-level constraints (sha256 64-hex pattern, semester/course slug
patterns, axis_key literal). R-10 보강: silent drop 검출용 4 unmatched
counts must land in the JSON manifest.
"""

from __future__ import annotations

from typing import Any

import pytest
from paideia_shared.schemas.combined_analysis_manifest import (
    CombinedAnalysisManifest,
)
from pydantic import ValidationError

_SHA = "0" * 64


def _baseline_kwargs(**overrides: Any) -> dict[str, Any]:
    """Build a minimum valid manifest dict; overrides apply on top."""
    base: dict[str, Any] = {
        "schema_version": "0.1.0",
        "module_version": "0.1.0",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "generated_at_utc": "2026-04-29T00:00:00Z",
        "factor_scores_sha256": _SHA,
        "cluster_assignment_sha256": _SHA,
        "cluster_names_sha256": _SHA,
        "student_metrics_sha256": _SHA,
        "student_master_sha256": _SHA,
        "diagnostic_response_sha256": _SHA,
        "n_students_combined": 30,
        "n_diagnostic_only": 3,
        "n_exam_only": 5,
        "n_both": 22,
        "n_neither": 0,
        "n_unmatched_factor_scores": 0,
        "n_unmatched_cluster_assignment": 0,
        "n_unmatched_student_metrics": 0,
        "n_off_roster_respondents": 0,
        "ruleset_version": "0.1.0",
        "regression_method": "OLS",
        "multiple_comparison_method": "BH-FDR",
        "posthoc_method_used": "Games_Howell",
        "run_seed": 0,
        "needs_map_schema_version": "0.1.1",
        "immersio_phase2_schema_version": "0.1.0",
        "top3_predictor_axes": ["motivation", "study_strategy", "time_availability"],
    }
    base.update(overrides)
    return base


def test_baseline_valid_manifest() -> None:
    m = CombinedAnalysisManifest(**_baseline_kwargs())
    assert m.n_students_combined == 30
    assert m.posthoc_method_used == "Games_Howell"
    assert m.top3_predictor_axes == [
        "motivation",
        "study_strategy",
        "time_availability",
    ]


def test_v1_count_consistency_passes_when_sum_matches() -> None:
    m = CombinedAnalysisManifest(
        **_baseline_kwargs(
            n_students_combined=10,
            n_diagnostic_only=2,
            n_exam_only=3,
            n_both=4,
            n_neither=1,
        )
    )
    assert m.n_students_combined == 10


def test_v1_count_consistency_fails_when_sum_mismatches() -> None:
    with pytest.raises(ValidationError, match="V1 count consistency"):
        CombinedAnalysisManifest(
            **_baseline_kwargs(
                n_students_combined=30,
                n_diagnostic_only=3,
                n_exam_only=5,
                n_both=22,
                n_neither=1,  # 3+5+22+1=31 != 30
            )
        )


def test_r10_unmatched_factor_scores_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(n_unmatched_factor_scores=-1))


def test_r10_unmatched_cluster_assignment_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(n_unmatched_cluster_assignment=-1))


def test_r10_unmatched_student_metrics_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(n_unmatched_student_metrics=-1))


def test_r10_off_roster_respondents_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(n_off_roster_respondents=-1))


def test_r10_unmatched_positive_values_land() -> None:
    """R-10: silent drop 검출 카운트가 모두 manifest 에 보존되어야 함."""
    m = CombinedAnalysisManifest(
        **_baseline_kwargs(
            n_unmatched_factor_scores=2,
            n_unmatched_cluster_assignment=1,
            n_unmatched_student_metrics=4,
            n_off_roster_respondents=3,
        )
    )
    assert m.n_unmatched_factor_scores == 2
    assert m.n_unmatched_cluster_assignment == 1
    assert m.n_unmatched_student_metrics == 4
    assert m.n_off_roster_respondents == 3


def test_v3_top3_at_most_three_axes_passes() -> None:
    m = CombinedAnalysisManifest(
        **_baseline_kwargs(top3_predictor_axes=["motivation", "study_strategy"])
    )
    assert len(m.top3_predictor_axes) == 2


def test_v3_top3_empty_list_passes() -> None:
    """0 significant axes ⇒ empty list (per data-model.md V3 note)."""
    m = CombinedAnalysisManifest(**_baseline_kwargs(top3_predictor_axes=[]))
    assert m.top3_predictor_axes == []


def test_v3_top3_more_than_three_rejected() -> None:
    with pytest.raises(ValidationError, match="V3 top3 length"):
        CombinedAnalysisManifest(
            **_baseline_kwargs(
                top3_predictor_axes=[
                    "motivation",
                    "study_strategy",
                    "time_availability",
                    "digital_efficacy",
                ]
            )
        )


def test_top3_invalid_axis_key_rejected() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(top3_predictor_axes=["not_an_axis"]))


def test_sha256_pattern_64_hex_required() -> None:
    """SHA256 fields must match ^[a-f0-9]{64}$ exactly."""
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(factor_scores_sha256="too-short"))


def test_cluster_names_sha256_required() -> None:
    """SPEC-GAP-001 sidecar fingerprint must land in the manifest (qa GAP-10)."""
    base = _baseline_kwargs()
    base.pop("cluster_names_sha256")
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**base)


def test_cluster_names_sha256_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(cluster_names_sha256="not-a-hash"))


def test_sha256_uppercase_hex_rejected() -> None:
    """Pattern enforces lowercase a-f only."""
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(factor_scores_sha256="A" * 64))


def test_regression_method_must_be_ols_literal() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(regression_method="GLS"))


def test_posthoc_method_na_when_k_eq_1() -> None:
    """k=1 폴백 시 posthoc_method_used == 'N/A' valid."""
    m = CombinedAnalysisManifest(**_baseline_kwargs(posthoc_method_used="N/A"))
    assert m.posthoc_method_used == "N/A"


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(unknown_field="x"))


def test_frozen_immutable() -> None:
    m = CombinedAnalysisManifest(**_baseline_kwargs())
    with pytest.raises(ValidationError):
        m.run_seed = 42  # type: ignore[misc]


def test_semester_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisManifest(**_baseline_kwargs(semester="2026/1"))


def test_run_seed_can_be_zero() -> None:
    m = CombinedAnalysisManifest(**_baseline_kwargs(run_seed=0))
    assert m.run_seed == 0
