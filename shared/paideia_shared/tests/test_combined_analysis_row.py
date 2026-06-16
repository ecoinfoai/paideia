"""TDD tests for ``CombinedAnalysisRow`` (M1, T005).

Validators V1-V6 per data-model.md:
- V1: student_id format (delegated to ``CanonicalStudentId``)
- V2: per-axis raw/z/missing consistency
- V3: exam_taken=False ⇒ all score None; 시험응시 == exam_taken
- V4: cluster triple all-None or all-not-None
- V5: 진단응답 == any axis raw populated
- V6: left-join preservation (학생 마스터에만 존재 = 진단응답=False AND 시험응시=False) is valid
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS
from paideia_shared.schemas.combined_analysis_row import CombinedAnalysisRow
from pydantic import ValidationError


def _base_row(**overrides: object) -> dict[str, object]:
    """Construct a minimally-valid row with all axes missing."""
    base: dict[str, object] = {
        "student_id": "2026000042",
        "name_kr": "홍길동",
        "on_roster": True,
        "section": "A",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "cluster_id": None,
        "cluster_label": None,
        "cluster_distance": None,
        "exam_taken": False,
        "total_score": None,
        "score_percent": None,
        "section_percentile": None,
        "cohort_percentile": None,
        "z_score": None,
        "chapter_correct_rates": {},
        "source_correct_rates": {},
        "difficulty_correct_rates": {},
        "expected_difficulty_correct_rates": {},
        "item_type_correct_rates": {},
        "interest_chapters_correct_rate": None,
        "aversion_chapters_correct_rate": None,
        "prior_readiness_q5": None,
        "prior_readiness_q6": None,
        "time_pattern_q21": None,
        "time_pattern_q22": None,
        "time_pattern_q23": None,
        "interest_topics_q9": None,
        "interest_topics_q10": None,
        "interest_topics_q11": None,
        "categorical_intent_q12": None,
        "categorical_intent_q13": None,
        "진단응답": False,
        "시험응시": False,
        "needs_map_schema_version": "0.1.1",
        "immersio_phase2_schema_version": "0.1.0",
    }
    for axis in STANDARD_AXIS_KEYS:
        base[f"{axis}_raw"] = None
        base[f"{axis}_z"] = None
        base[f"{axis}_missing"] = True
    base.update(overrides)
    return base


# V1 — student_id format (CanonicalStudentId)


def test_v1_student_id_must_be_10_digits() -> None:
    with pytest.raises(ValidationError):
        CombinedAnalysisRow(**_base_row(student_id="123"))
    with pytest.raises(ValidationError):
        CombinedAnalysisRow(**_base_row(student_id="abcdefghij"))


def test_v1_valid_student_id_passes() -> None:
    row = CombinedAnalysisRow(**_base_row())
    assert row.student_id == "2026000042"


# V2 — per-axis raw/z/missing consistency


def test_v2_raw_none_implies_missing_true() -> None:
    """raw=None but missing=False → ValueError."""
    overrides = _base_row(motivation_missing=False)
    # motivation_raw still None — inconsistent with missing=False
    with pytest.raises(ValidationError, match="V2 factor consistency"):
        CombinedAnalysisRow(**overrides)


def test_v2_raw_present_implies_missing_false() -> None:
    """raw present but missing=True → ValueError."""
    overrides = _base_row(
        motivation_raw=4.5, motivation_z=0.3, motivation_missing=True, 진단응답=True
    )
    with pytest.raises(ValidationError, match="V2 factor consistency"):
        CombinedAnalysisRow(**overrides)


def test_v2_raw_none_z_present_invalid() -> None:
    """raw=None but z=0.3 → ValueError (raw/z must agree on nullness)."""
    overrides = _base_row(motivation_raw=None, motivation_z=0.3, motivation_missing=True)
    with pytest.raises(ValidationError, match="V2 factor consistency"):
        CombinedAnalysisRow(**overrides)


def test_v2_all_axes_present_passes() -> None:
    overrides: dict[str, object] = {"진단응답": True}
    for axis in STANDARD_AXIS_KEYS:
        overrides[f"{axis}_raw"] = 4.0
        overrides[f"{axis}_z"] = 0.5
        overrides[f"{axis}_missing"] = False
    row = CombinedAnalysisRow(**_base_row(**overrides))
    assert row.motivation_raw == 4.0


# V3 — exam_taken consistency


def test_v3_exam_not_taken_with_score_invalid() -> None:
    overrides = _base_row(exam_taken=False, total_score=85.0, 시험응시=False)
    with pytest.raises(ValidationError, match="V3 exam_taken consistency"):
        CombinedAnalysisRow(**overrides)


def test_v3_시험응시_must_equal_exam_taken() -> None:
    overrides = _base_row(exam_taken=False, 시험응시=True)
    with pytest.raises(ValidationError, match="V3 exam_taken consistency"):
        CombinedAnalysisRow(**overrides)


def test_v3_exam_taken_with_scores_passes() -> None:
    overrides = _base_row(
        exam_taken=True,
        total_score=85.0,
        score_percent=85.0,
        section_percentile=90.0,
        cohort_percentile=88.0,
        z_score=1.2,
        시험응시=True,
    )
    row = CombinedAnalysisRow(**overrides)
    assert row.total_score == 85.0


# V4 — cluster triple consistency


def test_v4_partial_cluster_invalid() -> None:
    """Only cluster_id without label/distance → ValueError."""
    overrides = _base_row(cluster_id=1)  # label/distance still None
    with pytest.raises(ValidationError, match="V4 cluster consistency"):
        CombinedAnalysisRow(**overrides)


def test_v4_full_cluster_valid() -> None:
    overrides = _base_row(cluster_id=2, cluster_label="고동기/고전략", cluster_distance=0.42)
    row = CombinedAnalysisRow(**overrides)
    assert row.cluster_id == 2


def test_v4_no_cluster_valid() -> None:
    """All three None (k=1 fallback or non-respondent) — valid."""
    row = CombinedAnalysisRow(**_base_row())
    assert row.cluster_id is None


# V5 — 진단응답 flag consistency


def test_v5_진단응답_true_requires_axis_raw() -> None:
    """진단응답=True but all axes None → ValueError."""
    with pytest.raises(ValidationError, match="V5 diagnostic_response flag"):
        CombinedAnalysisRow(**_base_row(진단응답=True))


def test_v5_axis_present_requires_진단응답_true() -> None:
    """One axis raw present but 진단응답=False → ValueError."""
    overrides = _base_row(
        motivation_raw=4.5, motivation_z=0.3, motivation_missing=False, 진단응답=False
    )
    with pytest.raises(ValidationError, match="V5 diagnostic_response flag"):
        CombinedAnalysisRow(**overrides)


# V6 — left-join preservation: 진단응답=False AND 시험응시=False is VALID


def test_v6_neither_responder_nor_examined_valid() -> None:
    """학생 마스터에만 존재하는 학생 — 진단응답=False AND 시험응시=False → valid."""
    row = CombinedAnalysisRow(**_base_row())
    assert row.진단응답 is False
    assert row.시험응시 is False


# Identity edge — off-roster respondent (on_roster=False, name_kr=None, section=None)


def test_off_roster_respondent_valid() -> None:
    overrides = _base_row(
        on_roster=False,
        name_kr=None,
        section=None,
        motivation_raw=3.0,
        motivation_z=-0.5,
        motivation_missing=False,
        진단응답=True,
    )
    row = CombinedAnalysisRow(**overrides)
    assert row.on_roster is False
