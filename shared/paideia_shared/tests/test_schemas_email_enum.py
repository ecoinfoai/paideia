"""Contract tests for spec 006 enums (T006).

Verifies DispatchStatus (6 values), DispatchMode (2 values), CohortLabel
(3 values) per data-model.md §enum.
"""

from __future__ import annotations

import pytest

from paideia_shared.schemas import CohortLabel, DispatchMode, DispatchStatus


def test_dispatch_status_has_six_canonical_values() -> None:
    """DispatchStatus enum exposes exactly 6 spec-mandated values (FR-D08)."""
    assert {s.value for s in DispatchStatus} == {
        "success",
        "skipped",
        "failed",
        "temporary_failure",
        "dry_run",
        "test_dummy",
    }


def test_dispatch_status_member_access() -> None:
    """Each canonical value is reachable via attribute access."""
    assert DispatchStatus.SUCCESS.value == "success"
    assert DispatchStatus.SKIPPED.value == "skipped"
    assert DispatchStatus.FAILED.value == "failed"
    assert DispatchStatus.TEMPORARY_FAILURE.value == "temporary_failure"
    assert DispatchStatus.DRY_RUN.value == "dry_run"
    assert DispatchStatus.TEST_DUMMY.value == "test_dummy"


def test_dispatch_status_is_str_enum() -> None:
    """DispatchStatus comparisons against plain strings hold (StrEnum)."""
    assert DispatchStatus.SUCCESS == "success"
    assert "success" == DispatchStatus.SUCCESS


def test_dispatch_status_invalid_value_rejected() -> None:
    """Non-canonical strings raise ValueError on construction."""
    with pytest.raises(ValueError):
        DispatchStatus("nonexistent")


def test_dispatch_mode_has_two_values() -> None:
    """DispatchMode enum is binary: production/test (FR-D09)."""
    assert {m.value for m in DispatchMode} == {"production", "test"}


def test_dispatch_mode_member_access() -> None:
    assert DispatchMode.PRODUCTION.value == "production"
    assert DispatchMode.TEST.value == "test"


def test_cohort_label_has_three_values() -> None:
    """CohortLabel enum: low_score / rest / all (FR-H06)."""
    assert {c.value for c in CohortLabel} == {"low_score", "rest", "all"}


def test_cohort_label_member_access() -> None:
    assert CohortLabel.LOW_SCORE.value == "low_score"
    assert CohortLabel.REST.value == "rest"
    assert CohortLabel.ALL.value == "all"
