"""Contract tests for DispatchLogRow (T011).

Verifies all 13 columns + their validators and the locked column order
(contracts/email_log_csv.md). CSV round-trip is the primary use case.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)


def _valid_row_kwargs() -> dict:
    return dict(
        student_id="1234567890",
        name_kr="홍길동",
        email="student@example.com",
        pdf_filename="1234567890_홍길동.pdf",
        pdf_sha256="a" * 64,
        attempt_at_kst=datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc),
        mode=DispatchMode.PRODUCTION,
        status=DispatchStatus.SUCCESS,
        smtp_message_id="<abc@example.com>",
        error_kind="",
        error_detail="",
        exam_name="중간고사",
        cohort=CohortLabel.ALL,
    )


def test_column_order_locked() -> None:
    """Column order matches contracts/email_log_csv.md (13 columns)."""
    assert DispatchLogRow.COLUMN_ORDER == (
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


def test_valid_row_construction() -> None:
    row = DispatchLogRow(**_valid_row_kwargs())
    assert row.status == DispatchStatus.SUCCESS
    assert row.mode == DispatchMode.PRODUCTION
    assert row.cohort == CohortLabel.ALL


def test_csv_round_trip_preserves_columns() -> None:
    row = DispatchLogRow(**_valid_row_kwargs())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(DispatchLogRow.COLUMN_ORDER))
    writer.writeheader()
    dumped = row.model_dump(mode="json")
    writer.writerow({c: dumped[c] for c in DispatchLogRow.COLUMN_ORDER})
    assert buf.getvalue().splitlines()[0] == ",".join(DispatchLogRow.COLUMN_ORDER)


def test_skipped_row_allows_empty_email_and_sha256() -> None:
    kwargs = _valid_row_kwargs()
    kwargs["email"] = ""
    kwargs["pdf_sha256"] = ""
    kwargs["smtp_message_id"] = ""
    kwargs["status"] = DispatchStatus.SKIPPED
    kwargs["error_kind"] = "email_not_found"
    row = DispatchLogRow(**kwargs)
    assert row.email == ""
    assert row.pdf_sha256 == ""


def test_invalid_email_rejected() -> None:
    kwargs = _valid_row_kwargs()
    kwargs["email"] = "not-an-email"
    with pytest.raises(ValidationError):
        DispatchLogRow(**kwargs)


def test_invalid_sha256_rejected() -> None:
    kwargs = _valid_row_kwargs()
    kwargs["pdf_sha256"] = "short"
    with pytest.raises(ValidationError):
        DispatchLogRow(**kwargs)


def test_invalid_message_id_rejected() -> None:
    kwargs = _valid_row_kwargs()
    kwargs["smtp_message_id"] = "missing-brackets@example.com"
    with pytest.raises(ValidationError):
        DispatchLogRow(**kwargs)


def test_unknown_error_kind_rejected() -> None:
    kwargs = _valid_row_kwargs()
    kwargs["error_kind"] = "fake_error_kind"
    with pytest.raises(ValidationError):
        DispatchLogRow(**kwargs)


def test_known_error_kinds_accepted() -> None:
    kwargs = _valid_row_kwargs()
    kwargs["error_kind"] = "score_unavailable"
    DispatchLogRow(**kwargs)
    kwargs["error_kind"] = "gmail_api_quota_exceeded"
    DispatchLogRow(**kwargs)


def test_error_detail_max_length() -> None:
    kwargs = _valid_row_kwargs()
    kwargs["error_detail"] = "x" * 201
    with pytest.raises(ValidationError):
        DispatchLogRow(**kwargs)


def test_exam_name_must_be_non_empty() -> None:
    kwargs = _valid_row_kwargs()
    kwargs["exam_name"] = ""
    with pytest.raises(ValidationError):
        DispatchLogRow(**kwargs)


def test_status_enum_string_coercion() -> None:
    kwargs = _valid_row_kwargs()
    kwargs["status"] = "test_dummy"
    kwargs["mode"] = "test"
    row = DispatchLogRow(**kwargs)
    assert row.status == DispatchStatus.TEST_DUMMY
