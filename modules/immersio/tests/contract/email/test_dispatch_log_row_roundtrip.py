"""DispatchLogRow round-trip contract test (T063).

Hypothesis-driven: 100 random rows survive ``Pydantic → CSV → Pydantic``
round-trips without loss.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone, timedelta
from io import StringIO

import hypothesis.strategies as st
from hypothesis import given, settings

from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))


_VALID_ERROR_KINDS_NON_EMPTY: tuple[str, ...] = (
    "invalid_email",
    "email_not_found",
    "pdf_no_student_id",
    "pdf_filename_violation",
    "master_name_mismatch",
    "attachment_io_error",
    "attachment_size_exceeded",
    "gmail_api_invalid_recipient",
    "gmail_api_quota_exceeded",
    "gmail_api_rate_limit",
    "gmail_api_server_error",
    "gmail_api_unknown",
    "gmail_api_auth_failed",
    "gmail_api_domain_policy",
    "network_timeout",
    "score_unavailable",
)


def _student_id_strategy() -> st.SearchStrategy[str]:
    """10-digit student IDs (avoiding the `20\\d{8}` PII pattern in tests)."""
    return st.from_regex(r"^1[0-9]{9}$", fullmatch=True)


def _row_strategy() -> st.SearchStrategy[DispatchLogRow]:
    """Build a DispatchLogRow with random but valid field values."""
    return st.builds(
        lambda sid, status, mode, cohort, has_email, has_sha, error_kind, msec: DispatchLogRow(
            student_id=sid,
            name_kr="홍길동",
            email="ok@example.com" if has_email else "",
            pdf_filename=f"{sid}_홍길동.pdf",
            pdf_sha256="a" * 64 if has_sha else "",
            attempt_at_kst=datetime(2026, 5, 1, 12, msec % 60, 0, tzinfo=KST),
            mode=mode,
            status=status,
            smtp_message_id="<x@example.ac.kr>" if has_sha else "",
            error_kind=error_kind,
            error_detail="",
            exam_name="중간고사",
            cohort=cohort,
        ),
        sid=_student_id_strategy(),
        status=st.sampled_from(list(DispatchStatus)),
        mode=st.sampled_from(list(DispatchMode)),
        cohort=st.sampled_from(list(CohortLabel)),
        has_email=st.booleans(),
        has_sha=st.booleans(),
        error_kind=st.sampled_from(("",) + _VALID_ERROR_KINDS_NON_EMPTY),
        msec=st.integers(min_value=0, max_value=59),
    )


@settings(max_examples=100, deadline=None)
@given(row=_row_strategy())
def test_round_trip_csv_dictwriter_dictreader(row: DispatchLogRow) -> None:
    """csv.DictWriter → csv.DictReader → DispatchLogRow.model_validate
    must reconstruct an equal row.
    """
    buf = StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=list(DispatchLogRow.COLUMN_ORDER),
        lineterminator="\n",
    )
    writer.writeheader()
    dump = row.model_dump(mode="json")
    writer.writerow({c: dump[c] for c in DispatchLogRow.COLUMN_ORDER})

    buf.seek(0)
    reader = csv.DictReader(buf)
    [parsed_dict] = list(reader)
    parsed = DispatchLogRow.model_validate(parsed_dict)

    assert parsed.student_id == row.student_id
    assert parsed.status == row.status
    assert parsed.mode == row.mode
    assert parsed.cohort == row.cohort
    assert parsed.error_kind == row.error_kind
    assert parsed.email == row.email
    assert parsed.pdf_sha256 == row.pdf_sha256
    assert parsed.smtp_message_id == row.smtp_message_id
