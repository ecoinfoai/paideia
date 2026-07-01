"""Permission tests for report.py writer function (T008+T016).

RED → GREEN: verifies that write_dispatch_report_md produces an owner-only
(0600) output. Uses the assert_owner_only fixture from conftest.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from immersio.email.report import write_dispatch_report_md
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


def _manifest() -> EmailManifest:
    return EmailManifest(
        semester="2026-1",
        course_slug="anatomy",
        course_name_kr="인체구조와기능",
        exam_name="중간고사",
        sent_date_kst=date(2026, 5, 1),
        mode=DispatchMode.PRODUCTION,
        profile_name="alpha-prof",
        profile_kind="operator",
        profile_secrets_ref_env_var_name="PAIDEIA_GCP_SA_JSON_PATH_ALPHA",
        inputs=EmailManifestInputs(
            bronze_csv_path="/abs/csv",
            bronze_csv_sha256="a" * 64,
            gold_pdf_dir_path="/abs/pdfs",
            gold_pdf_count=3,
            silver_master_path="/abs/master",
            silver_master_sha256="b" * 64,
        ),
        outputs=EmailManifestOutputs(
            silver_mapping_path="/abs/mapping",
            silver_mapping_rows=3,
            dispatch_log_path="/abs/log",
            report_md_path="/abs/report",
        ),
        counts=EmailManifestCounts(
            success=2,
            skipped=0,
            failed=1,
            temporary_failure=0,
            dry_run=0,
            test_dummy=0,
        ),
        tool_version="0.1.1",
        started_at_kst=datetime(2026, 5, 1, 12, 0, 0, tzinfo=KST),
        completed_at_kst=datetime(2026, 5, 1, 12, 5, 0, tzinfo=KST),
    )


def _failed_row() -> DispatchLogRow:
    return DispatchLogRow(
        student_id="1234567003",
        name_kr="이민수",
        email="ok@example.com",
        pdf_filename="1234567003_이민수.pdf",
        pdf_sha256="c" * 64,
        attempt_at_kst=datetime(2026, 5, 1, 12, 1, 0, tzinfo=KST),
        mode=DispatchMode.PRODUCTION,
        status=DispatchStatus.FAILED,
        smtp_message_id="",
        error_kind="gmail_api_unknown",
        error_detail="Connection refused",
        exam_name="중간고사",
        cohort=CohortLabel.ALL,
    )


def test_write_dispatch_report_md_is_owner_only(tmp_path: Path, assert_owner_only) -> None:
    """write_dispatch_report_md must produce a 0600 file (PII: student_id, name_kr)."""
    summary = dict.fromkeys(DispatchStatus, 0)
    summary[DispatchStatus.SUCCESS] = 2
    summary[DispatchStatus.FAILED] = 1
    failed = _failed_row()
    data = DispatchReportData(
        manifest=_manifest(),
        summary_table=summary,
        failed_rows=[failed],
        skipped_rows=[],
        report_generated_at_kst=datetime(2026, 5, 1, 12, 5, 0, tzinfo=KST),
    )
    out = write_dispatch_report_md(data, tmp_path)
    assert_owner_only(out)
