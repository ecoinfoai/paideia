"""Validator coverage for paideia_shared.schemas.

Each Pydantic model exposes V1..V4 validators. We assert one positive and at
least one negative example per validator using ValidationError.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from paideia_shared.schemas import (
    DiagnosticMappingConfig,
    DiagnosticResponse,
    ExamItem,
    ExamResult,
    IngestInput,
    IngestManifest,
    IngestRowCount,
    MappingAxes,
    MappingColumn,
    MappingMetadata,
    StudentMaster,
)
from pydantic import ValidationError

# ---------- StudentMaster ----------

_BASE_MASTER: dict = {
    "student_id": "2026194999",
    "semester": "2026-1",
    "course_slug": "anatomy",
    "on_roster": True,
    "section": "A",
    "name_kr": "홍길동",
    "diagnostic_responded": True,
    "exam_taken": True,
    "exam_absent": False,
    "attendance_recorded": True,
    "exam_total_score": 87.5,
    "exam_max_score": 100.0,
    "attendance_present_count": 14,
    "attendance_absent_count": 1,
    "attendance_late_count": 1,
    "attendance_excused_count": 0,
    "axis_scores": {"motivation": 5.5, "anxiety": 3.2},
}


def test_student_master_v1_positive() -> None:
    StudentMaster(**_BASE_MASTER)


def test_student_master_v1_negative_inconsistent_absent() -> None:
    bad = {**_BASE_MASTER, "exam_taken": False, "exam_total_score": None, "exam_absent": False}
    # on_roster=True AND exam_taken=False ⇒ exam_absent must be True
    with pytest.raises(ValidationError, match="V1"):
        StudentMaster(**bad)


def test_student_master_v2_negative_score_without_exam() -> None:
    bad = {
        **_BASE_MASTER,
        "exam_taken": False,
        "exam_absent": True,
        "exam_total_score": 50.0,
    }
    with pytest.raises(ValidationError, match="V2"):
        StudentMaster(**bad)


def test_student_master_v3_negative_off_roster_with_section() -> None:
    bad = {
        **_BASE_MASTER,
        "on_roster": False,
        "section": "A",
        "exam_taken": True,
        "exam_absent": False,
    }
    with pytest.raises(ValidationError, match="V3"):
        StudentMaster(**bad)


def test_student_master_v3_positive_off_roster_no_section() -> None:
    StudentMaster(
        **{
            **_BASE_MASTER,
            "on_roster": False,
            "section": None,
            "exam_taken": False,
            "exam_total_score": None,
            "exam_absent": False,
        }
    )


def test_student_master_v4_negative_invalid_axis_key() -> None:
    bad = {**_BASE_MASTER, "axis_scores": {"Motivation": 5.0}}
    with pytest.raises(ValidationError, match="V4"):
        StudentMaster(**bad)


# ---------- DiagnosticResponse ----------

_BASE_DR: dict = {
    "student_id": "2026194999",
    "semester": "2026-1",
    "course_slug": "anatomy",
    "axis": "motivation",
    "axis_kind": "likert",
    "value_int": 6,
    "source_column": "Q01_나는_의학에_관심이_많다",
}


def test_dr_v1_likert_positive() -> None:
    DiagnosticResponse(**_BASE_DR)


def test_dr_v1_likert_negative_extra_field() -> None:
    bad = {**_BASE_DR, "value_text": "leak"}
    with pytest.raises(ValidationError, match="V1"):
        DiagnosticResponse(**bad)


def test_dr_v1_likert_negative_missing_int() -> None:
    bad = {**_BASE_DR, "value_int": None}
    with pytest.raises(ValidationError, match="V1"):
        DiagnosticResponse(**bad)


def test_dr_v2_multiselect_positive() -> None:
    DiagnosticResponse(
        student_id="2026194999",
        semester="2026-1",
        course_slug="anatomy",
        axis="interest",
        axis_kind="multiselect_onehot",
        option_key="신경계",
        value_bool=True,
        source_column="Q11_관심있는_챕터",
    )


def test_dr_v2_multiselect_negative_missing_option() -> None:
    bad = {
        "student_id": "2026194999",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "axis": "interest",
        "axis_kind": "multiselect_onehot",
        "value_bool": True,
        "source_column": "Q11_관심있는_챕터",
    }
    with pytest.raises(ValidationError, match="V2"):
        DiagnosticResponse(**bad)


def test_dr_v3_freetext_positive() -> None:
    DiagnosticResponse(
        student_id="2026194999",
        semester="2026-1",
        course_slug="anatomy",
        axis="anxiety",
        axis_kind="freetext",
        value_text="시험에 대한 불안이 큽니다.",
        source_column="Q62_시험에_대한_불안",
    )


def test_dr_v3_freetext_negative_missing_text() -> None:
    bad = {
        "student_id": "2026194999",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "axis": "anxiety",
        "axis_kind": "freetext",
        "source_column": "Q62_시험에_대한_불안",
    }
    with pytest.raises(ValidationError, match="V3"):
        DiagnosticResponse(**bad)


# ---------- ExamResult ----------


def test_exam_result_positive() -> None:
    ExamResult(
        student_id="2026194999",
        semester="2026-1",
        course_slug="anatomy",
        item_no=1,
        response="3",
        is_correct=True,
        score=2.0,
    )


def test_exam_result_v1_negative_no_response_with_correct() -> None:
    with pytest.raises(ValidationError, match="V1"):
        ExamResult(
            student_id="2026194999",
            semester="2026-1",
            course_slug="anatomy",
            item_no=1,
            response=None,
            is_correct=True,
            score=0.0,
        )


def test_exam_result_negative_item_zero() -> None:
    with pytest.raises(ValidationError):
        ExamResult(
            student_id="2026194999",
            semester="2026-1",
            course_slug="anatomy",
            item_no=0,
            response="1",
            is_correct=False,
            score=0.0,
        )


# ---------- ExamItem ----------


def test_exam_item_positive() -> None:
    ExamItem(
        semester="2026-1",
        course_slug="anatomy",
        item_no=1,
        chapter="1장 세포",
        source="textbook",
        expected_difficulty="medium",
        bloom="comprehension",
        answer_key="3",
        points=2.0,
        text="세포막의 주요 기능은?",
        distractors=["1", "2", "4", "5"],
    )


def test_exam_item_negative_negative_points() -> None:
    with pytest.raises(ValidationError):
        ExamItem(
            semester="2026-1",
            course_slug="anatomy",
            item_no=1,
            answer_key="3",
            points=-0.5,
        )


# ---------- IngestManifest ----------


def _five_inputs() -> list[IngestInput]:
    sha = "0" * 64
    return [
        IngestInput(role="diagnostic_csv", path="data/bronze/진단평가/d.csv", sha256=sha, encoding="utf-8"),
        IngestInput(role="exam_omr_xls", path="data/bronze/시험성적/A.xls", sha256=sha),
        IngestInput(role="attendance_xlsx", path="data/bronze/출석/a.xlsx", sha256=sha),
        IngestInput(role="exam_yaml", path="data/bronze/시험문제/q.yaml", sha256=sha),
        IngestInput(role="diagnostic_mapping_yaml", path="config/anatomy.yaml", sha256=sha, encoding="utf-8"),
    ]


_ROW_COUNTS = IngestRowCount(student_master=10, diagnostic_response=20, exam_result=30, exam_item=5)


def _base_manifest_kwargs() -> dict:
    return {
        "output_key": "2026-1-anatomy",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "course_name_kr": "인체구조와기능",
        "paideia_shared_version": "0.1.0",
        "immersio_version": "0.1.0",
        "mapping_version": 1,
        "inputs": _five_inputs(),
        "row_counts": _ROW_COUNTS,
        "created_at": datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
    }


def test_manifest_positive() -> None:
    IngestManifest(**_base_manifest_kwargs())


def test_manifest_v1_negative_output_key_mismatch() -> None:
    bad = {**_base_manifest_kwargs(), "output_key": "2026-1-microbiology"}
    with pytest.raises(ValidationError, match="V1"):
        IngestManifest(**bad)


def test_manifest_v2_negative_missing_role() -> None:
    inputs = _five_inputs()[:-1]
    bad = {**_base_manifest_kwargs(), "inputs": inputs}
    with pytest.raises(ValidationError, match="V2"):
        IngestManifest(**bad)


def test_manifest_v2_negative_duplicate_role() -> None:
    inputs = _five_inputs() + [_five_inputs()[0]]
    bad = {**_base_manifest_kwargs(), "inputs": inputs}
    with pytest.raises(ValidationError, match="V2"):
        IngestManifest(**bad)


def test_manifest_v3_negative_invalid_version() -> None:
    bad = {**_base_manifest_kwargs(), "paideia_shared_version": "not-a-version"}
    with pytest.raises(ValidationError, match="V3"):
        IngestManifest(**bad)


# ---------- DiagnosticMappingConfig ----------


_V1_1_QUANT_AXES = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def _base_mapping_kwargs() -> dict:
    """Build a v0.1.1-compliant mapping fixture: 8 quantitative likert columns
    + 1 identity + 1 auxiliary multiselect targeting an AuxiliaryGroupKey."""
    columns: list[MappingColumn] = [MappingColumn(source="학번", kind="identity")]
    for axis in _V1_1_QUANT_AXES:
        columns.append(
            MappingColumn(
                source=f"Q_{axis}",
                kind="likert",
                axis=axis,
                aggregate="mean",
            )
        )
    # Auxiliary multiselect — non-scoring, no aggregate=mean (V7).
    columns.append(
        MappingColumn(
            source="Q11_interest",
            kind="multiselect",
            axis="interest_topics",
        )
    )
    return {
        "metadata": MappingMetadata(
            semester="2026-1",
            course_slug="anatomy",
            course_name_kr="인체구조와기능",
            mapping_version=2,
        ),
        "columns": columns,
        "axes": MappingAxes(
            required=list(_V1_1_QUANT_AXES),
            optional=["interest_topics"],
        ),
    }


def test_mapping_positive() -> None:
    DiagnosticMappingConfig(**_base_mapping_kwargs())


def test_mapping_column_v1_negative_identity_with_axis() -> None:
    with pytest.raises(ValidationError, match="V1"):
        MappingColumn(source="학번", kind="identity", axis="something")


def test_mapping_column_v1_negative_non_identity_no_axis() -> None:
    with pytest.raises(ValidationError, match="V1"):
        MappingColumn(source="Q01", kind="likert", axis=None)


def test_mapping_v2_negative_two_identities() -> None:
    kwargs = _base_mapping_kwargs()
    extra_identity = MappingColumn(source="ID2", kind="identity")
    kwargs["columns"] = [extra_identity, *kwargs["columns"]]
    with pytest.raises(ValidationError, match="V2"):
        DiagnosticMappingConfig(**kwargs)


def test_mapping_v2_negative_zero_identity() -> None:
    kwargs = _base_mapping_kwargs()
    kwargs["columns"] = [c for c in kwargs["columns"] if c.kind != "identity"]
    with pytest.raises(ValidationError, match="V2"):
        DiagnosticMappingConfig(**kwargs)


def test_mapping_v3_negative_required_axis_unmapped() -> None:
    """A required axis that has no backing column raises V3 *before* V6 strict.

    Use a configuration that drops one likert column (study_strategy) but still
    keeps it in axes.required — V3 fires because no column maps to that axis.
    """
    kwargs = _base_mapping_kwargs()
    kwargs["columns"] = [
        c for c in kwargs["columns"] if c.axis != "study_strategy"
    ]
    # axes.required intentionally still names study_strategy — V3 violation.
    with pytest.raises(ValidationError, match="V3"):
        DiagnosticMappingConfig(**kwargs)


def test_mapping_v4_negative_inconsistent_aggregate() -> None:
    """Two likert columns on the same quantitative axis with mixed aggregates → V4."""
    kwargs = _base_mapping_kwargs()
    # Add a second motivation likert column with a different aggregate to fire V4.
    kwargs["columns"].append(
        MappingColumn(
            source="Q02_motivation_b",
            kind="likert",
            axis="motivation",
            aggregate="sum",
        )
    )
    with pytest.raises(ValidationError, match="V4"):
        DiagnosticMappingConfig(**kwargs)


def test_mapping_v4_positive_consistent_aggregate() -> None:
    """Two likert columns on the same axis with identical aggregates pass."""
    kwargs = _base_mapping_kwargs()
    kwargs["columns"].append(
        MappingColumn(
            source="Q02_motivation_b",
            kind="likert",
            axis="motivation",
            aggregate="mean",
        )
    )
    DiagnosticMappingConfig(**kwargs)
