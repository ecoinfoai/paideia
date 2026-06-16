"""GmailAPIDispatcher unit tests (T051)."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from googleapiclient.errors import HttpError
from immersio.email.composer import build_email_draft
from immersio.email.sender import (
    GmailAPIDispatcher,
    classify_gmail_api_error,
)
from paideia_shared.schemas import (
    DispatchMode,
    DispatchStatus,
    EmailMappingEntry,
    ProfessorProfile,
    StudentPDFBundle,
)


def _profile() -> ProfessorProfile:
    return ProfessorProfile.model_validate(
        yaml.safe_load(
            """
profile_kind: operator
profile_name: alpha-prof
sender:
  display_name: 알파교수
  email: alpha@example.ac.kr
send_account:
  email: noreply@example.ac.kr
institution:
  university_name: 알파대학교
  department_name: 알파학과
booking:
  google_calendar_url: https://calendar.google.com/calendar/u/0/appointments/abc
gmail_api:
  service_account_subject: noreply@example.ac.kr
  scopes:
    - https://www.googleapis.com/auth/gmail.send
secrets_ref:
  service_account_json_path_env: PAIDEIA_GCP_SA_JSON_PATH_ALPHA
operational_defaults:
  rate_per_minute: 20
  confirm_sample_size: 3
  attachment_max_bytes: 104857600
"""
        )
    )


def _draft(tmp_path: Path):
    pdf = tmp_path / "1234567001_홍길동.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF\n")
    return build_email_draft(
        profile=_profile(),
        mapping_entry=EmailMappingEntry(
            student_id="1234567001",
            email="student@example.com",
            source_row_index=0,
            original_timestamp=datetime(2026, 5, 1, 9, 0, 0, tzinfo=UTC),
        ),
        pdf_bundle=StudentPDFBundle(
            student_id="1234567001",
            name_kr="홍길동",
            pdf_path=pdf,
            pdf_filename=pdf.name,
            pdf_size_bytes=pdf.stat().st_size,
            pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
            body_first_page_text_normalized="학번1234567001",
            body_contains_student_id=True,
        ),
        course_name_kr="인체구조와기능",
        course_slug="anatomy",
        semester="2026-1",
        exam_name="중간고사",
        sent_date=date(2026, 5, 1),
        mode=DispatchMode.PRODUCTION,
    ), pdf


def _make_http_error(code: int, content: str = b"") -> HttpError:
    """Construct a minimal HttpError for classify tests."""
    resp = MagicMock()
    resp.status = code
    return HttpError(resp=resp, content=content if isinstance(content, bytes) else content.encode())


# ---------------------------------------------------------------------------
# classify_gmail_api_error — table-driven
# ---------------------------------------------------------------------------


def test_classify_400_invalid_recipient() -> None:
    status, kind = classify_gmail_api_error(_make_http_error(400, "Invalid To"))
    assert status == DispatchStatus.FAILED
    assert kind == "gmail_api_invalid_recipient"


def test_classify_401_auth_failed() -> None:
    status, kind = classify_gmail_api_error(_make_http_error(401, "invalid_grant"))
    assert status == DispatchStatus.FAILED
    assert kind == "gmail_api_auth_failed"


def test_classify_403_quota_exceeded() -> None:
    status, kind = classify_gmail_api_error(_make_http_error(403, "Mail sending quota exceeded"))
    assert status == DispatchStatus.TEMPORARY_FAILURE
    assert kind == "gmail_api_quota_exceeded"


def test_classify_403_domain_policy() -> None:
    status, kind = classify_gmail_api_error(_make_http_error(403, "Domain policy violation"))
    assert status == DispatchStatus.FAILED
    assert kind == "gmail_api_domain_policy"


def test_classify_429_rate_limit() -> None:
    status, kind = classify_gmail_api_error(_make_http_error(429, "Rate Limit Exceeded"))
    assert status == DispatchStatus.TEMPORARY_FAILURE
    assert kind == "gmail_api_rate_limit"


def test_classify_500_server_error() -> None:
    status, kind = classify_gmail_api_error(_make_http_error(500, "Internal"))
    assert status == DispatchStatus.TEMPORARY_FAILURE
    assert kind == "gmail_api_server_error"


def test_classify_unknown_code() -> None:
    status, kind = classify_gmail_api_error(_make_http_error(418, "I'm a teapot"))
    assert status == DispatchStatus.FAILED
    assert kind == "gmail_api_unknown"


# ---------------------------------------------------------------------------
# GmailAPIDispatcher.send_one — happy + 401 + missing-id
# ---------------------------------------------------------------------------


def test_send_one_success(tmp_path: Path) -> None:
    """Successful send returns SendResult.SUCCESS with Gmail server id."""
    draft, pdf = _draft(tmp_path)

    with (
        patch("immersio.email.sender.get_gmail_credentials") as mock_creds,
        patch("immersio.email.sender.build") as mock_build,
    ):
        mock_creds.return_value = MagicMock()
        service = MagicMock()
        service.users().messages().send.return_value.execute.return_value = {
            "id": "gmail-server-id-abc"
        }
        mock_build.return_value = service

        with GmailAPIDispatcher(_profile()) as dispatcher:
            result = dispatcher.send_one(draft, pdf_bytes=pdf.read_bytes())

    assert result.status == DispatchStatus.SUCCESS
    assert result.gmail_server_message_id == "gmail-server-id-abc"
    assert result.error_kind == ""


def test_send_one_401_invalid_grant(tmp_path: Path) -> None:
    """401 → SendResult.FAILED + gmail_api_auth_failed (caller exits 5)."""
    draft, pdf = _draft(tmp_path)

    with (
        patch("immersio.email.sender.get_gmail_credentials") as mock_creds,
        patch("immersio.email.sender.build") as mock_build,
    ):
        mock_creds.return_value = MagicMock()
        service = MagicMock()
        service.users().messages().send.return_value.execute.side_effect = _make_http_error(
            401, "invalid_grant"
        )
        mock_build.return_value = service

        with GmailAPIDispatcher(_profile()) as dispatcher:
            result = dispatcher.send_one(draft, pdf_bytes=pdf.read_bytes())

    assert result.status == DispatchStatus.FAILED
    assert result.error_kind == "gmail_api_auth_failed"
    assert result.gmail_server_message_id == ""


def test_send_one_response_missing_id(tmp_path: Path) -> None:
    """200 OK but no 'id' field → FAILED + gmail_api_unknown."""
    draft, pdf = _draft(tmp_path)

    with (
        patch("immersio.email.sender.get_gmail_credentials") as mock_creds,
        patch("immersio.email.sender.build") as mock_build,
    ):
        mock_creds.return_value = MagicMock()
        service = MagicMock()
        service.users().messages().send.return_value.execute.return_value = {}
        mock_build.return_value = service

        with GmailAPIDispatcher(_profile()) as dispatcher:
            result = dispatcher.send_one(draft, pdf_bytes=pdf.read_bytes())

    assert result.status == DispatchStatus.FAILED
    assert result.error_kind == "gmail_api_unknown"


def test_send_one_outside_context_manager_raises(tmp_path: Path) -> None:
    """Calling send_one without entering the context manager → RuntimeError."""
    draft, pdf = _draft(tmp_path)
    dispatcher = GmailAPIDispatcher(_profile())
    with pytest.raises(RuntimeError, match="outside context manager"):
        dispatcher.send_one(draft, pdf_bytes=pdf.read_bytes())
