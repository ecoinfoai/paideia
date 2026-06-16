"""Cross-entity validation for the four Silver outputs."""

from __future__ import annotations

from paideia_shared.schemas import (
    DiagnosticResponse,
    ExamItem,
    ExamResult,
    StudentMaster,
)

from .errors import DataIntegrityError, IngestViolation


def _integrity_violation(field: str, expected: str, found: object) -> IngestViolation:
    return IngestViolation(
        file_path="<cross-validate>",
        row_or_item_id=None,
        column_or_field=field,
        expected=expected,
        found=found,
    )


def validate_outputs(
    masters: list[StudentMaster],
    diag: list[DiagnosticResponse],
    exam: list[ExamResult],
    items: list[ExamItem],
) -> None:
    """Cross-reference all four entity lists and raise on any inconsistency.

    Student-ID-related collisions raise ``DataIntegrityError`` (CLI exit 4).
    Schema/format breaks raise ``ValueError`` (CLI exit 1 via the aggregator).

    Args:
        masters: List of StudentMaster rows (already individually validated).
        diag: List of DiagnosticResponse rows.
        exam: List of ExamResult rows.
        items: List of ExamItem rows.

    Raises:
        DataIntegrityError: For duplicate student IDs (cross-entity).
        ValueError: For non-ID structural breaks (item_no coverage etc.).
    """
    integrity_violations: list[IngestViolation] = []

    # 1. Unique student_id within StudentMaster (data-integrity)
    master_ids = [m.student_id for m in masters]
    if len(master_ids) != len(set(master_ids)):
        duplicates = sorted({sid for sid in master_ids if master_ids.count(sid) > 1})
        integrity_violations.append(
            _integrity_violation(
                "StudentMaster.student_id",
                "unique student_id per row",
                f"duplicates={duplicates}",
            )
        )

    # 2. Unique item_no within ExamItem (schema)
    item_keys = [(it.semester, it.course_slug, it.item_no) for it in items]
    if len(item_keys) != len(set(item_keys)):
        duplicates = sorted({k for k in item_keys if item_keys.count(k) > 1})
        raise ValueError(
            f"validate_outputs: duplicate (semester, course_slug, item_no) in "
            f"ExamItem: {duplicates}."
        )

    # 3. ExamResult.item_no ⊆ ExamItem.item_no (schema)
    valid_item_nos: set[int] = {it.item_no for it in items}
    orphans = sorted({e.item_no for e in exam if e.item_no not in valid_item_nos})
    if orphans:
        raise ValueError(
            f"validate_outputs: ExamResult references item_no not present in ExamItem: {orphans}."
        )

    # 4. ExamResult.student_id ⊆ StudentMaster.student_id (data-integrity)
    master_id_set = set(master_ids)
    exam_student_ids = {e.student_id for e in exam}
    diag_student_ids = {d.student_id for d in diag}
    missing_from_master = sorted((exam_student_ids | diag_student_ids) - master_id_set)
    if missing_from_master:
        integrity_violations.append(
            _integrity_violation(
                "ExamResult/DiagnosticResponse.student_id",
                "subset of StudentMaster.student_id",
                f"missing_from_master={missing_from_master}",
            )
        )

    # 5. ExamResult unique (student_id, item_no) (data-integrity)
    exam_keys = [(e.student_id, e.item_no) for e in exam]
    if len(exam_keys) != len(set(exam_keys)):
        duplicates = sorted({k for k in exam_keys if exam_keys.count(k) > 1})
        integrity_violations.append(
            _integrity_violation(
                "ExamResult.(student_id, item_no)",
                "unique pair per row",
                f"duplicates={duplicates}",
            )
        )

    if integrity_violations:
        raise DataIntegrityError(violations=integrity_violations)
