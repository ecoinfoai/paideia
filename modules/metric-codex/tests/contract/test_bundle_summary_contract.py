"""Contract tests for AdvisorBundleSummary (spec 013/014 T009).

Invariants:
1. assigned_count + len(unassigned_sids) == total_students_with_codex
2. sum(per_advisor_counts.values()) == assigned_count  (T009 v0.1.1)
3. unassigned_sids is ASC-sorted                       (T009 v0.1.1 MC-U29)
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


class TestAdvisorBundleSummaryPerAdvisorSum:
    """T009 v0.1.1 — sum(per_advisor_counts.values()) must equal assigned_count."""

    def test_per_advisor_sum_mismatch_raises(self):
        """sum(per_advisor_counts) > assigned_count → ValidationError (MC-U22)."""
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(
                total_students_with_codex=5,
                assigned_count=3,
                unassigned_sids=["2026194001", "2026194002"],
                advisor_count=2,
                # sum = 4, but assigned_count = 3
                per_advisor_counts={"advisor_A": 3, "advisor_B": 1},
            )

    def test_per_advisor_sum_less_raises(self):
        """sum(per_advisor_counts) < assigned_count → ValidationError."""
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(
                total_students_with_codex=5,
                assigned_count=3,
                unassigned_sids=["2026194001", "2026194002"],
                advisor_count=2,
                # sum = 2, but assigned_count = 3
                per_advisor_counts={"advisor_A": 1, "advisor_B": 1},
            )

    def test_per_advisor_sum_zero_assigned_empty_map_ok(self):
        """All unassigned: sum({}) == 0 == assigned_count=0 → valid."""
        bundle = AdvisorBundleSummary(
            total_students_with_codex=2,
            assigned_count=0,
            unassigned_sids=["2026194001", "2026194002"],
            advisor_count=0,
            per_advisor_counts={},
        )
        assert bundle.assigned_count == 0

    def test_per_advisor_sum_matches_assigned_ok(self):
        """Exact match: sum(per_advisor_counts) == assigned_count → valid."""
        bundle = AdvisorBundleSummary(
            total_students_with_codex=5,
            assigned_count=3,
            unassigned_sids=["2026194001", "2026194002"],
            advisor_count=2,
            per_advisor_counts={"advisor_A": 2, "advisor_B": 1},
        )
        assert sum(bundle.per_advisor_counts.values()) == bundle.assigned_count


class TestAdvisorBundleSummaryUnassignedSorted:
    """T009 v0.1.1 — unassigned_sids must be ASC-sorted (MC-U29)."""

    def test_unsorted_unassigned_raises(self):
        """Desc-sorted unassigned_sids → ValidationError."""
        with pytest.raises(ValidationError):
            AdvisorBundleSummary(
                total_students_with_codex=5,
                assigned_count=3,
                unassigned_sids=["2026194002", "2026194001"],  # reverse order
                advisor_count=2,
                per_advisor_counts={"advisor_A": 2, "advisor_B": 1},
            )

    def test_sorted_unassigned_ok(self):
        """ASC-sorted unassigned_sids → valid."""
        bundle = AdvisorBundleSummary(
            total_students_with_codex=5,
            assigned_count=3,
            unassigned_sids=["2026194001", "2026194002"],
            advisor_count=2,
            per_advisor_counts={"advisor_A": 2, "advisor_B": 1},
        )
        assert bundle.unassigned_sids == ["2026194001", "2026194002"]

    def test_single_unassigned_ok(self):
        """A single unassigned sid is trivially sorted → valid."""
        bundle = AdvisorBundleSummary(
            total_students_with_codex=4,
            assigned_count=3,
            unassigned_sids=["2026194001"],
            advisor_count=2,
            per_advisor_counts={"advisor_A": 2, "advisor_B": 1},
        )
        assert len(bundle.unassigned_sids) == 1

    def test_empty_unassigned_ok(self):
        """Empty unassigned_sids is trivially sorted → valid."""
        bundle = AdvisorBundleSummary(
            total_students_with_codex=3,
            assigned_count=3,
            unassigned_sids=[],
            advisor_count=2,
            per_advisor_counts={"advisor_A": 2, "advisor_B": 1},
        )
        assert bundle.unassigned_sids == []


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
