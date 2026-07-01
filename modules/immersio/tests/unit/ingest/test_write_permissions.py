"""T010+T018 — write_silver must produce owner-only PII parquets.

Security requirement: student_master, diagnostic_response, and exam_result
parquets carry student PII (student_id, name_kr) and must not be world- or
group-readable (DAR-01 / SC-006). exam_item is non-PII and not covered here.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from immersio.ingest.write import write_silver
from paideia_shared.schemas import (
    DiagnosticResponse,
    ExamItem,
    ExamResult,
    IngestInput,
    IngestManifest,
    IngestRowCount,
    StudentMaster,
)

_SHA256 = "a" * 64  # valid 64-char hex digest for test fixtures


def _make_inputs() -> list[IngestInput]:
    roles = [
        "diagnostic_csv",
        "exam_omr_xls",
        "attendance_xlsx",
        "exam_yaml",
        "diagnostic_mapping_yaml",
    ]
    return [IngestInput(role=r, path=f"{r}.file", sha256=_SHA256) for r in roles]


def _make_manifest(
    masters: list[StudentMaster],
    diag: list[DiagnosticResponse],
    exam: list[ExamResult],
    items: list[ExamItem],
) -> IngestManifest:
    return IngestManifest(
        output_key="2026-1-anatomy",
        semester="2026-1",
        course_slug="anatomy",
        paideia_shared_version="0.1.1",
        immersio_version="0.1.1",
        mapping_version=1,
        inputs=_make_inputs(),
        row_counts=IngestRowCount(
            student_master=len(masters),
            diagnostic_response=len(diag),
            exam_result=len(exam),
            exam_item=len(items),
        ),
        created_at=datetime(2026, 1, 1),
    )


def test_pii_parquets_are_owner_only(tmp_path: Path, assert_owner_only) -> None:
    """DAR-01: student_master, diagnostic_response, exam_result must be 0600."""
    masters = [
        StudentMaster(
            student_id="2026000001",
            semester="2026-1",
            course_slug="anatomy",
            on_roster=True,
            section="A",
            name_kr="홍길동",
            diagnostic_responded=True,
            exam_taken=True,
            exam_absent=False,
            attendance_recorded=True,
            exam_total_score=80.0,
            exam_max_score=100.0,
            attendance_present_count=10,
            attendance_absent_count=0,
            attendance_late_count=0,
            attendance_excused_count=0,
            axis_scores={"motivation": 4.0},
        )
    ]
    diag = [
        DiagnosticResponse(
            student_id="2026000001",
            semester="2026-1",
            course_slug="anatomy",
            axis="motivation",
            axis_kind="likert",
            value_int=4,
            source_column="Q1",
        )
    ]
    exam = [
        ExamResult(
            student_id="2026000001",
            semester="2026-1",
            course_slug="anatomy",
            item_no=1,
            response="1",
            is_correct=True,
            score=1.0,
        )
    ]
    items = [
        ExamItem(
            semester="2026-1",
            course_slug="anatomy",
            item_no=1,
            answer_key="1",
        )
    ]
    manifest = _make_manifest(masters, diag, exam, items)
    out_dir = tmp_path / "silver" / "2026-1-anatomy"

    write_silver(out_dir, masters, diag, exam, items, manifest)

    for name in (
        "student_master.parquet",
        "diagnostic_response.parquet",
        "exam_result.parquet",
    ):
        assert_owner_only(out_dir / name)
