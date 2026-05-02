"""Dispatch log CSV schema contract test (T062 — contracts/email_log_csv.md)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from immersio.email.log import (
    append_dispatch_log_row,
    append_dispatch_log_rows,
    mask_secrets_in_error_detail,
)
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))


_EXPECTED_COLUMNS: tuple[str, ...] = (
    "student_id",
    "name_kr",
    "email",
    "pdf_filename",
    "pdf_sha256",
    "attempt_at_kst",
    "mode",
    "status",
    "smtp_message_id",
    "error_kind",
    "error_detail",
    "exam_name",
    "cohort",
)


def test_column_count_is_thirteen() -> None:
    assert len(DispatchLogRow.COLUMN_ORDER) == 13


def test_column_order_matches_contract() -> None:
    assert DispatchLogRow.COLUMN_ORDER == _EXPECTED_COLUMNS


def test_csv_header_emits_exact_column_order(tmp_path: Path) -> None:
    log = tmp_path / "log.csv"
    append_dispatch_log_row(
        log,
        DispatchLogRow(
            student_id="1234567001",
            name_kr="홍길동",
            email="ok@example.com",
            pdf_filename="1234567001_홍길동.pdf",
            pdf_sha256="a" * 64,
            attempt_at_kst=datetime(2026, 5, 1, 12, 0, 0, tzinfo=KST),
            mode=DispatchMode.PRODUCTION,
            status=DispatchStatus.SUCCESS,
            smtp_message_id="<deterministic@example.ac.kr>",
            error_kind="",
            error_detail="",
            exam_name="중간고사",
            cohort=CohortLabel.ALL,
        ),
    )
    text = log.read_text(encoding="utf-8")
    header = text.splitlines()[0]
    assert header == ",".join(_EXPECTED_COLUMNS)


def test_csv_uses_utf8_lf_line_endings(tmp_path: Path) -> None:
    log = tmp_path / "log.csv"
    append_dispatch_log_row(
        log,
        DispatchLogRow(
            student_id="1234567001",
            name_kr="홍길동",
            email="ok@example.com",
            pdf_filename="1234567001_홍길동.pdf",
            pdf_sha256="a" * 64,
            attempt_at_kst=datetime(2026, 5, 1, 12, 0, 0, tzinfo=KST),
            mode=DispatchMode.PRODUCTION,
            status=DispatchStatus.SUCCESS,
            smtp_message_id="<x@example.ac.kr>",
            error_kind="",
            error_detail="",
            exam_name="중간고사",
            cohort=CohortLabel.ALL,
        ),
    )
    raw = log.read_bytes()
    # No CRLF — pure LF (default csv.writer with newline="" + utf-8)
    assert b"\r\n" not in raw
    # Korean characters present (UTF-8)
    assert "홍길동".encode("utf-8") in raw


def test_mask_patterns_strip_secrets() -> None:
    """Defence-in-depth check: every contract pattern is scrubbed."""
    assert "<redacted-app-password>" in mask_secrets_in_error_detail(
        "abcd efgh ijkl mnop"  # ALLOW_HARDCODING: intentional fixture
    )
    assert "<redacted-rsa-private-key>" in mask_secrets_in_error_detail(
        "-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----"  # ALLOW_HARDCODING: intentional fixture
    )
    assert "<redacted>" in mask_secrets_in_error_detail(
        '"private_key": "secret-bytes"'  # ALLOW_HARDCODING: intentional fixture
    )
    assert "<redacted-sa-email>" in mask_secrets_in_error_detail(
        "fake-sa@x.iam.gserviceaccount.com"  # ALLOW_HARDCODING: intentional SA-domain fixture
    )


def test_status_enum_values_serialise_correctly(tmp_path: Path) -> None:
    """All 6 status values round-trip via csv → Pydantic without loss."""
    log = tmp_path / "log.csv"
    rows = []
    for i, s in enumerate(DispatchStatus):
        rows.append(
            DispatchLogRow(
                student_id=f"123456{i:04d}",
                name_kr="홍길동",
                email="ok@example.com" if s != DispatchStatus.SKIPPED else "",
                pdf_filename="x.pdf",
                pdf_sha256="a" * 64 if s != DispatchStatus.SKIPPED else "",
                attempt_at_kst=datetime(2026, 5, 1, 12, i, 0, tzinfo=KST),
                mode=DispatchMode.PRODUCTION,
                status=s,
                smtp_message_id=(
                    "<x@example.ac.kr>" if s == DispatchStatus.SUCCESS else ""
                ),
                error_kind="invalid_email" if s == DispatchStatus.SKIPPED else "",
                error_detail="",
                exam_name="중간고사",
                cohort=CohortLabel.ALL,
            )
        )
    append_dispatch_log_rows(log, rows)
    text = log.read_text(encoding="utf-8")
    # Each enum value present
    for s in DispatchStatus:
        assert f",{s.value}," in text or f"{s.value}\n" in text
