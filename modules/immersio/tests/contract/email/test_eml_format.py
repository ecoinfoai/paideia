"""EML format contract test (T037 — contracts/email_mime_format.md).

Materialises a single EmailMessage via the composer and verifies the 8
canonical headers, single-part body, single attachment, and absence of
forbidden headers.
"""

from __future__ import annotations

import email
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from immersio.email.composer import build_email_draft, to_email_message
from paideia_shared.schemas import (
    DispatchMode,
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


@pytest.fixture
def composed_message(tmp_path: Path):
    pdf = tmp_path / "1234567890_홍길동.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake content\n%%EOF\n")
    bundle = StudentPDFBundle(
        student_id="1234567890",
        name_kr="홍길동",
        pdf_path=pdf,
        pdf_filename=pdf.name,
        pdf_size_bytes=pdf.stat().st_size,
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        body_first_page_text_normalized="학번1234567890",
        body_contains_student_id=True,
    )
    entry = EmailMappingEntry(
        student_id="1234567890",
        email="student@example.com",
        source_row_index=0,
        original_timestamp=datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc),
    )
    draft = build_email_draft(
        profile=_profile(),
        mapping_entry=entry,
        pdf_bundle=bundle,
        course_name_kr="인체구조와기능",
        course_slug="anatomy",
        semester="2026-1",
        exam_name="중간고사",
        sent_date=date(2026, 5, 1),
        mode=DispatchMode.PRODUCTION,
    )
    return to_email_message(draft, pdf_bytes=pdf.read_bytes())


def test_eight_canonical_headers_present(composed_message) -> None:
    for header in (
        "From",
        "Reply-To",
        "To",
        "Subject",
        "Date",
        "Message-ID",
        "MIME-Version",
        "Content-Type",
    ):
        assert composed_message[header] is not None, f"missing {header}"


def test_forbidden_headers_absent(composed_message) -> None:
    for header in ("Cc", "Bcc", "Sender", "Return-Path", "X-Original-To", "Delivered-To"):
        assert composed_message[header] is None, f"forbidden {header} present"


def test_to_header_single_recipient(composed_message) -> None:
    assert composed_message["To"] == "student@example.com"
    assert "," not in composed_message["To"]
    assert ";" not in composed_message["To"]


def test_content_type_is_multipart_mixed(composed_message) -> None:
    ct = composed_message["Content-Type"]
    assert ct.startswith("multipart/mixed")
    assert 'boundary="boundary-1234567890-2026-05-01"' in ct


def test_message_id_uses_send_account_domain(composed_message) -> None:
    assert composed_message["Message-ID"] == (
        "<1234567890.2026-05-01.anatomy.2026-1@example.ac.kr>"
    )


def test_date_header_kst_noon(composed_message) -> None:
    """Date header serialises KST 12:00 (RFC 5322)."""
    date_value = composed_message["Date"]
    assert "12:00:00 +0900" in date_value


def test_attachment_count_is_one(composed_message) -> None:
    payload_parts = composed_message.get_payload()
    attachments = [
        p for p in payload_parts if p.get_content_disposition() == "attachment"
    ]
    assert len(attachments) == 1


def test_attachment_is_pdf(composed_message) -> None:
    payload_parts = composed_message.get_payload()
    pdf_parts = [p for p in payload_parts if p.get_content_type() == "application/pdf"]
    assert len(pdf_parts) == 1


def test_body_text_part_present(composed_message) -> None:
    payload_parts = composed_message.get_payload()
    text_parts = [p for p in payload_parts if p.get_content_type() == "text/plain"]
    assert len(text_parts) == 1


def test_round_trip_via_email_parser(composed_message) -> None:
    raw = composed_message.as_bytes()
    parsed = email.message_from_bytes(raw)
    assert parsed["Message-ID"] == composed_message["Message-ID"]
    assert parsed["To"] == composed_message["To"]
