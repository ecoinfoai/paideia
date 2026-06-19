"""Contract tests for AdvisorBundleSummary (spec 013 T009).

Invariant: assigned_count + len(unassigned_sids) == total_students_with_codex
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas.metric_codex import AdvisorBundleSummary
from pydantic import ValidationError


def _valid_bundle(**overrides):
    base = dict(
        total_students_with_codex=5,
        assigned_count=3,
        unassigned_sids=["2026194001", "2026194002"],
        advisor_count=2,
        per_advisor_counts={"advisor_A": 2, "advisor_B": 1},
    )
    base.update(overrides)
    return base


class TestAdvisorBundleSummaryValid:
    def test_valid_bundle_constructs(self):
        bundle = AdvisorBundleSummary(**_valid_bundle())
        assert bundle.total_students_with_codex == 5
        assert bundle.assigned_count == 3
        assert len(bundle.unassigned_sids) == 2

    def test_zero_unassigned(self):
        bundle = AdvisorBundleSummary(
            total_students_with_codex=3,
            assigned_count=3,
            unassigned_sids=[],
            advisor_count=1,
            per_advisor_counts={"advisor_A": 3},
        )
        assert bundle.unassigned_sids == []

    def test_all_unassigned(self):
        bundle = AdvisorBundleSummary(
            total_students_with_codex=2,
            assigned_count=0,
            unassigned_sids=["2026194001", "2026194002"],
            advisor_count=0,
            per_advisor_counts={},
        )
        assert bundle.advisor_count == 0

    def test_zero_students(self):
        bundle = AdvisorBundleSummary(
            total_students_with_codex=0,
            assigned_count=0,
            unassigned_sids=[],
            advisor_count=0,
            per_advisor_counts={},
        )
        assert bundle.total_students_with_codex == 0


class TestAdvisorBundleSummaryInvariant:
    def test_invariant_violation_raises(self):
        """assigned_count + len(unassigned_sids) != total → ValueError."""
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(
                total_students_with_codex=10,
                assigned_count=3,
                unassigned_sids=["2026194001", "2026194002"],  # 3 + 2 = 5 != 10
                advisor_count=2,
                per_advisor_counts={"advisor_A": 3},
            )

    def test_invariant_assigned_too_large_raises(self):
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(
                total_students_with_codex=3,
                assigned_count=4,  # 4 + 0 = 4 != 3
                unassigned_sids=[],
                advisor_count=1,
                per_advisor_counts={"advisor_A": 4},
            )

    def test_invariant_wrong_unassigned_count_raises(self):
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(
                total_students_with_codex=5,
                assigned_count=3,
                unassigned_sids=["2026194001"],  # 3 + 1 = 4 != 5
                advisor_count=1,
                per_advisor_counts={"advisor_A": 3},
            )


class TestAdvisorBundleSummaryBounds:
    def test_negative_total_raises(self):
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(**_valid_bundle(total_students_with_codex=-1))

    def test_negative_assigned_raises(self):
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(**_valid_bundle(assigned_count=-1))

    def test_negative_advisor_count_raises(self):
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(**_valid_bundle(advisor_count=-1))

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(**_valid_bundle(unknown="x"))

    def test_immutable(self):
        bundle = AdvisorBundleSummary(**_valid_bundle())
        with pytest.raises((ValidationError, TypeError)):
            bundle.assigned_count = 99  # type: ignore[misc]
