"""log.py unit tests (T058) — append + flock + idempotent + masking."""

from __future__ import annotations

import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from immersio.email.log import (
    DispatchLockError,
    RetryMode,
    STATUS_KR,
    append_dispatch_log_row,
    append_dispatch_log_rows,
    idempotent_skip_filter,
    mask_secrets_in_error_detail,
    read_dispatch_log,
)
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))


def _row(
    sid: str,
    status: DispatchStatus,
    *,
    error_kind: str = "",
    error_detail: str = "",
    minute: int = 0,
) -> DispatchLogRow:
    return DispatchLogRow(
        student_id=sid,
        name_kr="홍길동",
        email="ok@example.com",
        pdf_filename=f"{sid}_홍길동.pdf",
        pdf_sha256="a" * 64,
        attempt_at_kst=datetime(2026, 5, 1, 12, minute, 0, tzinfo=KST),
        mode=DispatchMode.PRODUCTION,
        status=status,
        smtp_message_id="<deterministic@example.ac.kr>",
        error_kind=error_kind,
        error_detail=error_detail,
        exam_name="중간고사",
        cohort=CohortLabel.ALL,
    )


# ---------------------------------------------------------------------------
# Append + header behavior
# ---------------------------------------------------------------------------


def test_append_creates_header_on_first_write(tmp_path: Path) -> None:
    log = tmp_path / "log.csv"
    append_dispatch_log_row(log, _row("1234567001", DispatchStatus.SUCCESS))
    text = log.read_text(encoding="utf-8")
    assert text.splitlines()[0] == ",".join(DispatchLogRow.COLUMN_ORDER)


def test_append_no_duplicate_header_on_second_write(tmp_path: Path) -> None:
    log = tmp_path / "log.csv"
    append_dispatch_log_row(log, _row("1234567001", DispatchStatus.SUCCESS))
    append_dispatch_log_row(log, _row("1234567002", DispatchStatus.SUCCESS))
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("student_id,")
    assert lines[1].startswith("1234567001,")
    assert lines[2].startswith("1234567002,")


def test_append_calls_fsync(tmp_path: Path) -> None:
    """fsync must be called after each append (durability — ADR-005)."""
    log = tmp_path / "log.csv"
    with patch("immersio.email.log.os.fsync") as mock_fsync:
        append_dispatch_log_row(log, _row("1234567001", DispatchStatus.SUCCESS))
    assert mock_fsync.call_count >= 1


def test_bulk_append_writes_all_rows(tmp_path: Path) -> None:
    log = tmp_path / "log.csv"
    rows = [
        _row("1234567001", DispatchStatus.SUCCESS, minute=0),
        _row("1234567002", DispatchStatus.FAILED, error_kind="gmail_api_unknown", minute=1),
        _row("1234567003", DispatchStatus.SKIPPED, error_kind="invalid_email", minute=2),
    ]
    append_dispatch_log_rows(log, rows)
    read_back = read_dispatch_log(log)
    assert len(read_back) == 3
    assert {r.student_id for r in read_back} == {
        "1234567001",
        "1234567002",
        "1234567003",
    }


# ---------------------------------------------------------------------------
# flock — concurrent run rejection
# ---------------------------------------------------------------------------


def test_flock_blocks_concurrent_writer(tmp_path: Path) -> None:
    """LOCK_EX|LOCK_NB: a parallel acquirer raises DispatchLockError."""
    import fcntl
    import os

    log = tmp_path / "log.csv"
    log.touch()
    # Hold the lock from a separate fd
    fd_a = os.open(log, os.O_RDWR)
    fcntl.flock(fd_a, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(DispatchLockError, match="FR-D02"):
            append_dispatch_log_row(
                log, _row("1234567001", DispatchStatus.SUCCESS)
            )
    finally:
        fcntl.flock(fd_a, fcntl.LOCK_UN)
        os.close(fd_a)


# ---------------------------------------------------------------------------
# idempotent_skip_filter — RetryMode semantics
# ---------------------------------------------------------------------------


def test_idempotent_filter_default_skips_only_success(tmp_path: Path) -> None:
    log = [
        _row("1234567001", DispatchStatus.SUCCESS),
        _row("1234567002", DispatchStatus.FAILED, minute=1),
        _row("1234567003", DispatchStatus.SKIPPED, minute=2),
        _row("1234567004", DispatchStatus.TEMPORARY_FAILURE, minute=3),
    ]
    targets = ["1234567001", "1234567002", "1234567003", "1234567004", "1234567005"]
    keep = idempotent_skip_filter(targets, log, RetryMode.DEFAULT)
    # Default skips success only → re-tries failed/skipped/temp + new
    assert keep == ["1234567002", "1234567003", "1234567004", "1234567005"]


def test_idempotent_filter_retry_failed_keeps_only_failed_temp(
    tmp_path: Path,
) -> None:
    log = [
        _row("1234567001", DispatchStatus.SUCCESS),
        _row("1234567002", DispatchStatus.FAILED, minute=1),
        _row("1234567003", DispatchStatus.SKIPPED, minute=2),
        _row("1234567004", DispatchStatus.TEMPORARY_FAILURE, minute=3),
    ]
    targets = ["1234567001", "1234567002", "1234567003", "1234567004"]
    keep = idempotent_skip_filter(targets, log, RetryMode.RETRY_FAILED)
    assert keep == ["1234567002", "1234567004"]


def test_idempotent_filter_retry_skipped_keeps_only_skipped(
    tmp_path: Path,
) -> None:
    log = [
        _row("1234567001", DispatchStatus.SUCCESS),
        _row("1234567002", DispatchStatus.FAILED, minute=1),
        _row("1234567003", DispatchStatus.SKIPPED, minute=2),
        _row("1234567004", DispatchStatus.TEMPORARY_FAILURE, minute=3),
    ]
    targets = ["1234567001", "1234567002", "1234567003", "1234567004"]
    keep = idempotent_skip_filter(targets, log, RetryMode.RETRY_SKIPPED)
    assert keep == ["1234567003"]


def test_idempotent_filter_uses_latest_attempt_at_kst(tmp_path: Path) -> None:
    """Multiple log rows for same sid: latest attempt_at_kst wins."""
    log = [
        _row("1234567001", DispatchStatus.FAILED, minute=0),
        _row("1234567001", DispatchStatus.SUCCESS, minute=5),  # later
    ]
    targets = ["1234567001"]
    keep = idempotent_skip_filter(targets, log, RetryMode.DEFAULT)
    assert keep == []  # latest = success → skipped


def test_idempotent_filter_empty_log_returns_all(tmp_path: Path) -> None:
    targets = ["1234567001", "1234567002"]
    assert idempotent_skip_filter(targets, [], RetryMode.DEFAULT) == targets


# ---------------------------------------------------------------------------
# mask_secrets_in_error_detail
# ---------------------------------------------------------------------------


def test_mask_app_password() -> None:
    text = "auth failed with abcd efgh ijkl mnop"
    masked = mask_secrets_in_error_detail(text)
    assert "abcd efgh ijkl mnop" not in masked
    assert "<redacted-app-password>" in masked


def test_mask_rsa_private_key_block() -> None:
    text = (
        "context: -----BEGIN PRIVATE KEY-----\nfake-bytes\n"
        "-----END PRIVATE KEY-----"
    )
    masked = mask_secrets_in_error_detail(text)
    assert "BEGIN PRIVATE KEY" not in masked
    assert "fake-bytes" not in masked
    assert "<redacted-rsa-private-key>" in masked


def test_mask_json_private_key_field() -> None:
    text = '{"private_key": "fake-bytes"}'
    masked = mask_secrets_in_error_detail(text)
    assert "fake-bytes" not in masked
    assert '"private_key": "<redacted>"' in masked


def test_mask_sa_email_domain() -> None:
    text = "rejected sender fake-sa@fake-project.iam.gserviceaccount.com"
    masked = mask_secrets_in_error_detail(text)
    assert "fake-sa@fake-project" not in masked
    assert "<redacted-sa-email>" in masked


def test_mask_empty_input() -> None:
    assert mask_secrets_in_error_detail("") == ""


# ---------------------------------------------------------------------------
# Round-trip + Korean status mapping
# ---------------------------------------------------------------------------


def test_csv_round_trip_preserves_columns(tmp_path: Path) -> None:
    log = tmp_path / "log.csv"
    original = _row("1234567001", DispatchStatus.SUCCESS, minute=42)
    append_dispatch_log_row(log, original)
    [round_tripped] = read_dispatch_log(log)
    assert round_tripped.student_id == original.student_id
    assert round_tripped.status == original.status
    assert round_tripped.smtp_message_id == original.smtp_message_id


def test_attempt_at_kst_iso8601_format(tmp_path: Path) -> None:
    """attempt_at_kst lands in CSV as ISO 8601 with KST offset."""
    log = tmp_path / "log.csv"
    append_dispatch_log_row(log, _row("1234567001", DispatchStatus.SUCCESS))
    text = log.read_text(encoding="utf-8")
    # +09:00 offset literal
    assert "+09:00" in text


def test_status_kr_mapping_complete() -> None:
    """All 6 DispatchStatus values must have Korean labels."""
    for status in DispatchStatus:
        assert status in STATUS_KR
        assert STATUS_KR[status]
