"""Contract tests for NeedsMapManifest + sub-models (M7, FR-023)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas import (
    LLMCallStat,
    NeedsMapInput,
    NeedsMapManifest,
    NeedsMapPhaseRowCount,
)
from pydantic import ValidationError

_OK_SHA = "0" * 64
_ALT_SHA = "1" * 64


def _input() -> NeedsMapInput:
    return NeedsMapInput(
        diagnostic_response_path="data/silver/immersio/2026-1-anatomy/diagnostic_response.parquet",
        diagnostic_response_sha256=_OK_SHA,
        student_master_path="data/silver/immersio/2026-1-anatomy/student_master.parquet",
        student_master_sha256=_ALT_SHA,
        diagnostic_mapping_path="data/bronze/매핑/anatomy.diagnostic.yaml",
        diagnostic_mapping_sha256=_OK_SHA,
        keyword_dictionary_path="paideia_shared/keywords/ko.yaml",
        keyword_dictionary_sha256=_ALT_SHA,
        missing_policy_source={
            "motivation": "yaml",
            "study_strategy": "default",
        },
    )


def _manifest(**overrides: object) -> NeedsMapManifest:
    base: dict[str, object] = {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "output_key": "2026-1-anatomy",
        "module_version": "needs-map/0.1.0",
        "created_at_utc": "2026-04-27T00:00:00Z",
        "inputs": _input(),
        "standard_axes_used": ["motivation", "study_strategy"],
        "standard_axes_skipped": ["material_preference"],
        "phases_executed": ["A", "B"],
        "rows_per_phase": [
            NeedsMapPhaseRowCount(phase="A", rows_written=6),
            NeedsMapPhaseRowCount(phase="B", rows_written=194),
        ],
        "pii_redaction_validated": True,
    }
    base.update(overrides)
    return NeedsMapManifest(**base)  # type: ignore[arg-type]


# --- field-level validation ---


def test_sha256_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        NeedsMapInput(
            diagnostic_response_path="x",
            diagnostic_response_sha256="not-hex",
            student_master_path="y",
            student_master_sha256=_OK_SHA,
            diagnostic_mapping_path="z",
            diagnostic_mapping_sha256=_OK_SHA,
        )


def test_iso8601_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        _manifest(created_at_utc="2026-04-27 00:00:00")


def test_iso8601_passes_for_valid_string() -> None:
    m = _manifest()
    assert m.created_at_utc == "2026-04-27T00:00:00Z"


def test_match_rate_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(free_text_dictionary_match_rate=1.5)


def test_cluster_k_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(cluster_k_used=7)


# --- model validators ---


def test_v1_output_key_must_match_semester_course() -> None:
    with pytest.raises(ValidationError) as exc:
        _manifest(output_key="2026-2-anatomy")
    assert "V1" in str(exc.value)


def test_v2_used_and_skipped_axes_disjoint() -> None:
    with pytest.raises(ValidationError) as exc:
        _manifest(
            standard_axes_used=["motivation", "study_strategy"],
            standard_axes_skipped=["motivation"],
        )
    assert "V2" in str(exc.value)


def test_v3_duplicate_llm_sites_rejected() -> None:
    dup = [
        LLMCallStat(site="cluster_naming", attempted=2, succeeded=2, fallback=0),
        LLMCallStat(site="cluster_naming", attempted=1, succeeded=0, fallback=1),
    ]
    with pytest.raises(ValidationError) as exc:
        _manifest(llm_calls=dup)
    assert "V3" in str(exc.value)


def test_v4_duplicate_phase_rowcounts_rejected() -> None:
    dup = [
        NeedsMapPhaseRowCount(phase="A", rows_written=1),
        NeedsMapPhaseRowCount(phase="A", rows_written=2),
    ]
    with pytest.raises(ValidationError) as exc:
        _manifest(rows_per_phase=dup)
    assert "V4" in str(exc.value)


# --- LLMCallStat counts ---


def test_llm_call_stat_succeeded_plus_fallback_le_attempted() -> None:
    LLMCallStat(site="free_text", attempted=10, succeeded=6, fallback=4)  # OK
    with pytest.raises(ValidationError) as exc:
        LLMCallStat(site="free_text", attempted=10, succeeded=7, fallback=4)
    assert "V1" in str(exc.value)


def test_llm_call_stat_failure_kinds_default_empty() -> None:
    stat = LLMCallStat(site="coaching", attempted=0, succeeded=0, fallback=0)
    assert stat.failure_kinds == {}


# --- missing_policy_source provenance ---


def test_missing_policy_source_accepts_yaml_or_default() -> None:
    m = _manifest()
    assert m.inputs.missing_policy_source == {
        "motivation": "yaml",
        "study_strategy": "default",
    }


def test_missing_policy_source_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        NeedsMapInput(
            diagnostic_response_path="x",
            diagnostic_response_sha256=_OK_SHA,
            student_master_path="y",
            student_master_sha256=_OK_SHA,
            diagnostic_mapping_path="z",
            diagnostic_mapping_sha256=_OK_SHA,
            missing_policy_source={"motivation": "guessed"},  # type: ignore[dict-item]
        )


def test_missing_policy_source_rejects_non_standard_axis() -> None:
    with pytest.raises(ValidationError):
        NeedsMapInput(
            diagnostic_response_path="x",
            diagnostic_response_sha256=_OK_SHA,
            student_master_path="y",
            student_master_sha256=_OK_SHA,
            diagnostic_mapping_path="z",
            diagnostic_mapping_sha256=_OK_SHA,
            missing_policy_source={"self_regulation": "yaml"},  # type: ignore[dict-item]
        )
