"""Combine four parsed sources into per-student StudentMaster rows."""

from __future__ import annotations

from typing import Any

import pandas as pd
from paideia_shared.schemas import (
    CourseSlug,
    ExamItem,
    ExamResult,
    SemesterCode,
    StudentMaster,
)


def _merge_axis_keys(
    axis_scores_by_student: dict[str, dict[str, float | None]],
) -> set[str]:
    keys: set[str] = set()
    for scores in axis_scores_by_student.values():
        keys.update(scores.keys())
    return keys


def combine_sources(
    diagnostic_df: pd.DataFrame,
    exam_responses_df: pd.DataFrame,
    exam_summary_df: pd.DataFrame,
    attendance_df: pd.DataFrame,
    axis_scores_by_student: dict[str, dict[str, float | None]],
    items: list[ExamItem],
    semester: SemesterCode,
    course_slug: CourseSlug,
) -> tuple[list[StudentMaster], list[ExamResult]]:
    """Combine the four parsed sources into StudentMaster + ExamResult rows.

    Args:
        diagnostic_df: DataFrame indexed by student_id (from parse_diagnostic_csv).
        exam_responses_df: Long-form (student_id, section, item_no, response).
        exam_summary_df: (student_id, section, exam_taken, exam_total_score, exam_max_score).
        attendance_df: (student_id, name_kr, attendance_present_count, ...).
        axis_scores_by_student: Output of apply_mapping aggregator.
        items: Validated list[ExamItem] (used to compute is_correct).
        semester: SemesterCode.
        course_slug: CourseSlug.

    Returns:
        Tuple ``(student_masters, exam_results)`` sorted by student_id (and item_no).

    Raises:
        ValueError: If diagnostic and attendance student_ids differ in shape that
            prevents canonical resolution.
    """
    # Roster = students appearing in attendance (the authoritative class roster source).
    roster: set[str] = set(attendance_df["student_id"].tolist())
    diag_ids: set[str] = set(diagnostic_df.index.tolist())
    exam_ids: set[str] = set(exam_summary_df["student_id"].tolist())

    all_ids: set[str] = roster | diag_ids | exam_ids
    declared_axes = _merge_axis_keys(axis_scores_by_student)

    name_lookup: dict[str, str | None] = {}
    attendance_lookup: dict[str, dict[str, Any]] = {}
    for _, row in attendance_df.iterrows():
        sid = row["student_id"]
        attendance_lookup[sid] = row.to_dict()
        name_kr = row.get("name_kr")
        if name_kr is not None and not (isinstance(name_kr, float) and pd.isna(name_kr)):
            name_lookup[sid] = str(name_kr)
        else:
            name_lookup[sid] = None
    exam_lookup: dict[str, dict[str, Any]] = {
        row["student_id"]: row.to_dict() for _, row in exam_summary_df.iterrows()
    }

    student_masters: list[StudentMaster] = []

    for student_id in sorted(all_ids):
        on_roster = student_id in roster
        diagnostic_responded = student_id in diag_ids
        attendance_recorded = student_id in roster
        exam_record = exam_lookup.get(student_id)
        exam_taken = bool(exam_record["exam_taken"]) if exam_record else False
        exam_total_score = (
            float(exam_record["exam_total_score"])
            if exam_record and exam_record.get("exam_total_score") is not None
            else None
        )
        exam_max_score = (
            float(exam_record["exam_max_score"])
            if exam_record and exam_record.get("exam_max_score") is not None
            else None
        )
        exam_absent = on_roster and not exam_taken

        section: str | None = None
        if on_roster and exam_record is not None and exam_record.get("section"):
            section = str(exam_record["section"])

        attendance_record = attendance_lookup.get(student_id, {})
        attendance_present = (
            int(attendance_record.get("attendance_present_count"))
            if attendance_record.get("attendance_present_count") is not None
            else (None if not attendance_recorded else 0)
        )
        attendance_absent = (
            int(attendance_record.get("attendance_absent_count"))
            if attendance_record.get("attendance_absent_count") is not None
            else (None if not attendance_recorded else 0)
        )
        attendance_late = (
            int(attendance_record.get("attendance_late_count"))
            if attendance_record.get("attendance_late_count") is not None
            else (None if not attendance_recorded else 0)
        )
        attendance_excused = (
            int(attendance_record.get("attendance_excused_count"))
            if attendance_record.get("attendance_excused_count") is not None
            else (None if not attendance_recorded else 0)
        )

        # axis_scores: ensure every declared axis appears (None for missing)
        student_axis_scores = dict(axis_scores_by_student.get(student_id, {}))
        for axis_key in declared_axes:
            student_axis_scores.setdefault(axis_key, None)

        student_masters.append(
            StudentMaster(
                student_id=student_id,
                semester=semester,
                course_slug=course_slug,
                on_roster=on_roster,
                section=section,  # type: ignore[arg-type]
                name_kr=name_lookup.get(student_id),
                diagnostic_responded=diagnostic_responded,
                exam_taken=exam_taken,
                exam_absent=exam_absent,
                attendance_recorded=attendance_recorded,
                exam_total_score=exam_total_score,
                exam_max_score=exam_max_score if exam_taken else None,
                attendance_present_count=attendance_present,
                attendance_absent_count=attendance_absent,
                attendance_late_count=attendance_late,
                attendance_excused_count=attendance_excused,
                axis_scores=dict(sorted(student_axis_scores.items())),
            )
        )

    # ExamResult rows: map response → is_correct using items metadata
    answer_by_item = {item.item_no: item.answer_key for item in items}
    points_by_item = {item.item_no: item.points for item in items}

    exam_results: list[ExamResult] = []
    for _, row in exam_responses_df.iterrows():
        student_id = row["student_id"]
        item_no = int(row["item_no"])
        response = row["response"]
        if response is None or (isinstance(response, float) and pd.isna(response)):
            response_value: str | None = None
            is_correct: bool | None = None
            score: float = 0.0
        else:
            response_value = str(response)
            is_correct = response_value == answer_by_item.get(item_no)
            score = float(points_by_item.get(item_no, 0.0)) if is_correct else 0.0
        exam_results.append(
            ExamResult(
                student_id=student_id,
                semester=semester,
                course_slug=course_slug,
                item_no=item_no,
                response=response_value,
                is_correct=is_correct,
                score=score,
            )
        )

    exam_results = sorted(exam_results, key=lambda e: (e.student_id, e.item_no))
    return student_masters, exam_results
