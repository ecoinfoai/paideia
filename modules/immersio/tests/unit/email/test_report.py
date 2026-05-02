"""report.py unit tests (T061)."""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import pytest

from immersio.email.report import (
    COHORT_KR,
    STATUS_KR,
    write_dispatch_report_md,
)
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchReportData,
    DispatchStatus,
    EmailManifest,
    EmailManifestCounts,
    EmailManifestInputs,
    EmailManifestOutputs,
)

KST = timezone(timedelta(hours=9))


def _row(
    sid: str,
    status: DispatchStatus,
    *,
    error_kind: str = "",
    error_detail: str = "",
) -> DispatchLogRow:
    return DispatchLogRow(
        student_id=sid,
        name_kr="홍길동",
        email="ok@example.com",
        pdf_filename=f"{sid}_홍길동.pdf",
        pdf_sha256="a" * 64,
        attempt_at_kst=datetime(2026, 5, 1, 12, 0, 0, tzinfo=KST),
        mode=DispatchMode.PRODUCTION,
        status=status,
        smtp_message_id="<deterministic@example.ac.kr>",
        error_kind=error_kind,
        error_detail=error_detail,
        exam_name="중간고사",
        cohort=CohortLabel.ALL,
    )


def _manifest(*, mode: DispatchMode = DispatchMode.PRODUCTION) -> EmailManifest:
    return EmailManifest(
        semester="2026-1",
        course_slug="anatomy",
        course_name_kr="인체구조와기능",
        exam_name="중간고사",
        sent_date_kst=date(2026, 5, 1),
        mode=mode,
        profile_name="alpha-prof",
        profile_kind="operator",
        profile_secrets_ref_env_var_name="PAIDEIA_GCP_SA_JSON_PATH_ALPHA",
        inputs=EmailManifestInputs(
            bronze_csv_path="/abs/csv",
            bronze_csv_sha256="a" * 64,
            gold_pdf_dir_path="/abs/pdfs",
            gold_pdf_count=5,
            silver_master_path="/abs/master",
            silver_master_sha256="b" * 64,
        ),
        outputs=EmailManifestOutputs(
            silver_mapping_path="/abs/mapping",
            silver_mapping_rows=5,
            dispatch_log_path="/abs/log",
            report_md_path="/abs/report",
        ),
        counts=EmailManifestCounts(
            success=3, skipped=1, failed=1,
            temporary_failure=0, dry_run=0, test_dummy=0,
        ),
        tool_version="0.1.0",
        started_at_kst=datetime(2026, 5, 1, 12, 0, 0, tzinfo=KST),
        completed_at_kst=datetime(2026, 5, 1, 12, 5, 0, tzinfo=KST),
    )


def test_production_report_renders_summary_table(tmp_path: Path) -> None:
    rows = [
        _row("1234567001", DispatchStatus.SUCCESS),
        _row("1234567002", DispatchStatus.SUCCESS),
        _row("1234567003", DispatchStatus.SUCCESS),
        _row(
            "1234567004",
            DispatchStatus.SKIPPED,
            error_kind="invalid_email",
            error_detail="csv has no email",
        ),
        _row(
            "1234567005",
            DispatchStatus.FAILED,
            error_kind="gmail_api_invalid_recipient",
            error_detail="Invalid To",
        ),
    ]
    summary = {s: 0 for s in DispatchStatus}
    for r in rows:
        summary[r.status] += 1
    data = DispatchReportData(
        manifest=_manifest(),
        summary_table=summary,
        failed_rows=[r for r in rows if r.status == DispatchStatus.FAILED],
        skipped_rows=[r for r in rows if r.status == DispatchStatus.SKIPPED],
        report_generated_at_kst=datetime(2026, 5, 1, 12, 5, 0, tzinfo=KST),
    )
    out = write_dispatch_report_md(data, tmp_path)
    text = out.read_text(encoding="utf-8")
    # Korean summary table present
    assert "성공" in text
    assert "누락" in text
    assert "실패" in text
    # Failed + skipped sections present
    assert "## 실패 학생 명단" in text
    assert "## 누락 학생 명단" in text
    # Each student appears exactly once in their respective table
    assert text.count("1234567005") == 1
    assert text.count("1234567004") == 1


def test_dry_run_report_only_shows_dry_run(tmp_path: Path) -> None:
    rows = [_row(f"123456700{i}", DispatchStatus.DRY_RUN) for i in range(5)]
    summary = {s: 0 for s in DispatchStatus}
    summary[DispatchStatus.DRY_RUN] = 5
    data = DispatchReportData(
        manifest=_manifest(),
        summary_table=summary,
        failed_rows=[],
        skipped_rows=[],
        report_generated_at_kst=datetime(2026, 5, 1, 12, 0, 0, tzinfo=KST),
    )
    out = write_dispatch_report_md(data, tmp_path)
    text = out.read_text(encoding="utf-8")
    assert "미리보기" in text
    # Failed/skipped sections absent (no rows)
    assert "## 실패 학생 명단" not in text
    assert "## 누락 학생 명단" not in text


def test_summary_counts_sum_to_student_count(tmp_path: Path) -> None:
    rows = [
        _row("1234567001", DispatchStatus.SUCCESS),
        _row("1234567002", DispatchStatus.SUCCESS),
        _row("1234567003", DispatchStatus.SKIPPED, error_kind="invalid_email"),
    ]
    summary = {s: 0 for s in DispatchStatus}
    for r in rows:
        summary[r.status] += 1
    assert sum(summary.values()) == 3


def test_status_kr_and_cohort_kr_complete() -> None:
    """All enum values have Korean labels (FR-D04)."""
    for s in DispatchStatus:
        assert s in STATUS_KR
    for c in CohortLabel:
        assert c in COHORT_KR
