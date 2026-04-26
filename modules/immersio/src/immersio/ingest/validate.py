"""Cross-entity validation for the four Silver outputs."""

from __future__ import annotations

from paideia_shared.schemas import (
    DiagnosticResponse,
    ExamItem,
    ExamResult,
    StudentMaster,
)


def validate_outputs(
    masters: list[StudentMaster],
    diag: list[DiagnosticResponse],
    exam: list[ExamResult],
    items: list[ExamItem],
) -> None:
    """Cross-reference all four entity lists and raise on any inconsistency.

    Args:
        masters: List of StudentMaster rows (already individually validated).
        diag: List of DiagnosticResponse rows.
        exam: List of ExamResult rows.
        items: List of ExamItem rows.

    Raises:
        ValueError: If any cross-entity invariant is violated.
    """
    # 1. Unique student_id within StudentMaster
    master_ids = [m.student_id for m in masters]
    if len(master_ids) != len(set(master_ids)):
        duplicates = sorted({sid for sid in master_ids if master_ids.count(sid) > 1})
        raise ValueError(
            f"validate_outputs: duplicate student_id in StudentMaster: {duplicates}."
        )

    # 2. Unique item_no within ExamItem (and unique key (semester, course_slug, item_no))
    item_keys = [(it.semester, it.course_slug, it.item_no) for it in items]
    if len(item_keys) != len(set(item_keys)):
        duplicates = sorted({k for k in item_keys if item_keys.count(k) > 1})
        raise ValueError(
            f"validate_outputs: duplicate (semester, course_slug, item_no) in "
            f"ExamItem: {duplicates}."
        )

    # 3. ExamResult.item_no ⊆ ExamItem.item_no
    valid_item_nos: set[int] = {it.item_no for it in items}
    orphans = sorted({e.item_no for e in exam if e.item_no not in valid_item_nos})
    if orphans:
        raise ValueError(
            f"validate_outputs: ExamResult references item_no not present in "
            f"ExamItem: {orphans}."
        )

    # 4. ExamResult.student_id ⊆ StudentMaster.student_id
    master_id_set = set(master_ids)
    exam_student_ids = {e.student_id for e in exam}
    diag_student_ids = {d.student_id for d in diag}
    missing_from_master = sorted(
        (exam_student_ids | diag_student_ids) - master_id_set
    )
    if missing_from_master:
        raise ValueError(
            f"validate_outputs: ExamResult/DiagnosticResponse student_id not "
            f"present in StudentMaster: {missing_from_master}."
        )

    # 5. ExamResult unique (student_id, item_no)
    exam_keys = [(e.student_id, e.item_no) for e in exam]
    if len(exam_keys) != len(set(exam_keys)):
        duplicates = sorted({k for k in exam_keys if exam_keys.count(k) > 1})
        raise ValueError(
            f"validate_outputs: duplicate (student_id, item_no) in ExamResult: {duplicates}."
        )
