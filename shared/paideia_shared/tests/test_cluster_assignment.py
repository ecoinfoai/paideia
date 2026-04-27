"""Contract tests for ClusterAssignmentRow / ClusterCandidate / ClusterReport (T058, M5)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas import (
    ClusterAssignmentRow,
    ClusterCandidate,
    ClusterReport,
)
from pydantic import ValidationError


def _row(student_id: str = "2026194042", cluster_id: int = 0, distance: float | None = 0.5) -> ClusterAssignmentRow:
    return ClusterAssignmentRow(
        student_id=student_id, cluster_id=cluster_id, distance_to_centroid=distance
    )


def _report(**overrides: object) -> ClusterReport:
    base: dict[str, object] = {
        "rows": [_row("2026194000", 0), _row("2026194001", 1)],
        "k_used": 2,
        "silhouette_used": 0.42,
        "candidates": [
            ClusterCandidate(k=2, silhouette_score=0.42),
            ClusterCandidate(k=3, silhouette_score=0.31),
        ],
        "cluster_names": {0: "고동기형", 1: "저동기형"},
        "naming_source": "rule",
        "weak_structure_warning": False,
        "sample_too_small_warning": False,
        "k_override_reason": None,
        "semester": "2026-1",
        "course_slug": "anatomy",
        "module_version": "needs-map/0.1.0",
    }
    base.update(overrides)
    return ClusterReport(**base)  # type: ignore[arg-type]


# --- ClusterAssignmentRow ---


def test_cluster_id_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        _row(cluster_id=-1)


def test_distance_to_centroid_may_be_none() -> None:
    row = _row(distance=None)
    assert row.distance_to_centroid is None


# --- ClusterCandidate ---


@pytest.mark.parametrize("k", [2, 3, 4, 5, 6])
def test_candidate_k_in_range(k: int) -> None:
    cand = ClusterCandidate(k=k, silhouette_score=0.3)
    assert cand.k == k


@pytest.mark.parametrize("bad_k", [1, 7, 0, -1])
def test_candidate_k_out_of_range_rejected(bad_k: int) -> None:
    with pytest.raises(ValidationError):
        ClusterCandidate(k=bad_k, silhouette_score=0.3)


# --- ClusterReport V1: k_used must be in candidates when k_used > 1 ---


def test_v1_k_used_must_be_in_candidates() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _report(
            k_used=4,
            candidates=[ClusterCandidate(k=2, silhouette_score=0.3)],
            cluster_names={0: "X", 1: "Y", 2: "Z", 3: "W"},
            rows=[
                _row("2026194000", 0),
                _row("2026194001", 1),
                _row("2026194002", 2),
                _row("2026194003", 3),
            ],
        )


def test_v1_k_used_one_skips_candidates_check() -> None:
    """k=1 fallback (sample_too_small or weak_structure) bypasses V1."""
    report = _report(
        k_used=1,
        silhouette_used=None,
        candidates=[ClusterCandidate(k=2, silhouette_score=0.1)],
        cluster_names={0: "단일 군집"},
        rows=[_row("2026194000", 0), _row("2026194001", 0)],
        weak_structure_warning=False,
        sample_too_small_warning=True,
    )
    assert report.k_used == 1


# --- ClusterReport V2: cluster_names must cover all used cluster_ids ---


def test_v2_cluster_names_missing_id_rejected() -> None:
    with pytest.raises(ValidationError, match="V2"):
        _report(
            cluster_names={0: "고동기형"},  # missing cluster_id=1
        )


def test_v2_cluster_names_extra_id_rejected() -> None:
    with pytest.raises(ValidationError, match="V2"):
        _report(
            cluster_names={0: "X", 1: "Y", 2: "Z"},  # cluster_id=2 not used
        )


# --- ClusterReport V3: silhouette_used null pairing with k_used ---


def test_v3_k_one_requires_silhouette_none() -> None:
    with pytest.raises(ValidationError, match="V3"):
        _report(
            k_used=1,
            silhouette_used=0.1,
            candidates=[ClusterCandidate(k=2, silhouette_score=0.1)],
            cluster_names={0: "단일"},
            rows=[_row("2026194000", 0)],
            sample_too_small_warning=True,
        )


def test_v3_k_above_one_requires_silhouette_float() -> None:
    with pytest.raises(ValidationError, match="V3"):
        _report(silhouette_used=None)


# --- naming_source enum ---


@pytest.mark.parametrize("source", ["rule", "llm", "llm_fallback"])
def test_naming_source_accepts_three_values(source: str) -> None:
    report = _report(naming_source=source)
    assert report.naming_source == source


def test_naming_source_rejects_other_values() -> None:
    with pytest.raises(ValidationError):
        _report(naming_source="manual")


# --- k_override_reason optional ---


def test_k_override_reason_default_none() -> None:
    assert _report().k_override_reason is None


def test_k_override_reason_string_accepted() -> None:
    report = _report(
        k_override_reason="user --k 2 explicit override; auto-recommend would have been 3",
    )
    assert "explicit override" in (report.k_override_reason or "")
