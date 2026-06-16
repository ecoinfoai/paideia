"""Composer tests (T036) — 14 scenarios covering body / headers / determinism."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from immersio.email.composer import (
    EMAIL_BODY_TEMPLATE_KO,
    build_email_draft,
    to_email_message,
)
from paideia_shared.schemas import (
    DispatchMode,
    EmailMappingEntry,
    ProfessorProfile,
    StudentPDFBundle,
)

KST = timezone(timedelta(hours=9))


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


def _entry() -> EmailMappingEntry:
    return EmailMappingEntry(
        student_id="1234567890",
        email="student@example.com",
        source_row_index=0,
        original_timestamp=datetime(2026, 5, 1, 9, 0, 0, tzinfo=UTC),
    )


def _bundle(tmp_path: Path) -> StudentPDFBundle:
    pdf = tmp_path / "1234567890_홍길동.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF\n")
    return StudentPDFBundle(
        student_id="1234567890",
        name_kr="홍길동",
        pdf_path=pdf,
        pdf_filename=pdf.name,
        pdf_size_bytes=pdf.stat().st_size,
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        body_first_page_text_normalized="학번1234567890",
        body_contains_student_id=True,
    )


def _kwargs(tmp_path: Path) -> dict:
    return dict(
        profile=_profile(),
        mapping_entry=_entry(),
        pdf_bundle=_bundle(tmp_path),
        course_name_kr="인체구조와기능",
        course_slug="anatomy",
        semester="2026-1",
        exam_name="중간고사",
        sent_date=date(2026, 5, 1),
        mode=DispatchMode.PRODUCTION,
    )


# ---------------------------------------------------------------------------
# Body / variable substitution
# ---------------------------------------------------------------------------


def test_body_substitutes_six_variables(tmp_path: Path) -> None:
    draft = build_email_draft(**_kwargs(tmp_path))
    body = draft.body_text
    assert "알파대학교" in body
    assert "알파학과" in body
    assert "알파교수" in body
    assert "중간고사" in body
    assert "https://calendar.google.com" in body
    assert "2026년 5월 1일" in body


def test_body_no_residual_placeholder(tmp_path: Path) -> None:
    """FR-G06: zero `{name}` placeholders in the rendered body."""
    draft = build_email_draft(**_kwargs(tmp_path))
    assert re.search(r"\{[a-z_]+\}", draft.body_text) is None


def test_body_template_constant_only_has_variable_placeholders() -> None:
    """The template constant must contain ONLY placeholder variables, never
    student/professor identifier values (FR-G06)."""
    placeholders = re.findall(r"\{([a-z_]+)\}", EMAIL_BODY_TEMPLATE_KO)
    assert set(placeholders) == {
        "university_name",
        "department_name",
        "sender_name",
        "exam_name",
        "google_calendar_url",
        "sent_date_kr",
    }


# ---------------------------------------------------------------------------
# Headers (8 canonical)
# ---------------------------------------------------------------------------


def test_subject_plain_korean_format(tmp_path: Path) -> None:
    draft = build_email_draft(**_kwargs(tmp_path))
    assert draft.subject == "[인체구조와기능] 중간고사 결과 보고서 — 홍길동(1234567890)"


def test_subject_encoded_rfc2047(tmp_path: Path) -> None:
    draft = build_email_draft(**_kwargs(tmp_path))
    assert "=?utf-8?" in draft.subject_encoded.lower()


def test_to_header_single_recipient(tmp_path: Path) -> None:
    draft = build_email_draft(**_kwargs(tmp_path))
    assert draft.to_header == "student@example.com"


def test_to_header_rejects_comma(tmp_path: Path) -> None:
    """The Pydantic validator rejects multi-recipient at the model layer."""
    kwargs = _kwargs(tmp_path)
    kwargs["override_to"] = "a@example.com, b@example.com"
    with pytest.raises(Exception):
        build_email_draft(**kwargs)


def test_from_header_combines_course_and_sender(tmp_path: Path) -> None:
    draft = build_email_draft(**_kwargs(tmp_path))
    # email.utils.formataddr RFC 2047 encodes Korean display name
    assert "noreply@example.ac.kr" in draft.from_header
    # Display name encoded form contains UTF-8 base64 marker
    assert "=?utf-8?" in draft.from_header.lower()


def test_reply_to_header_uses_sender_email(tmp_path: Path) -> None:
    draft = build_email_draft(**_kwargs(tmp_path))
    assert "alpha@example.ac.kr" in draft.reply_to_header


def test_date_header_kst_noon(tmp_path: Path) -> None:
    draft = build_email_draft(**_kwargs(tmp_path))
    assert draft.date_header.tzinfo is not None
    assert draft.date_header.hour == 12
    assert draft.date_header.minute == 0
    assert draft.date_header.second == 0


def test_message_id_deterministic_with_send_account_domain(tmp_path: Path) -> None:
    draft = build_email_draft(**_kwargs(tmp_path))
    assert draft.message_id == ("<1234567890.2026-05-01.anatomy.2026-1@example.ac.kr>")


def test_mime_boundary_deterministic(tmp_path: Path) -> None:
    draft = build_email_draft(**_kwargs(tmp_path))
    assert draft.mime_boundary == "boundary-1234567890-2026-05-01"


# ---------------------------------------------------------------------------
# Attachment + EmailMessage materialisation
# ---------------------------------------------------------------------------


def test_attachment_sha256_carried_through(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    kwargs = _kwargs(tmp_path)
    kwargs["pdf_bundle"] = bundle
    draft = build_email_draft(**kwargs)
    assert draft.attachment_sha256 == bundle.pdf_sha256


def test_to_email_message_has_eight_headers(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path)
    bundle = kwargs["pdf_bundle"]
    draft = build_email_draft(**kwargs)
    msg = to_email_message(draft, pdf_bytes=bundle.pdf_path.read_bytes())
    assert msg["From"] is not None
    assert msg["Reply-To"] is not None
    assert msg["To"] is not None
    assert msg["Subject"] is not None
    assert msg["Date"] is not None
    assert msg["Message-ID"] is not None
    assert msg["MIME-Version"] == "1.0"
    assert msg["Content-Type"].startswith("multipart/mixed")
    # Forbidden headers absent
    assert msg["Cc"] is None
    assert msg["Bcc"] is None
    assert msg["Sender"] is None


def test_to_email_message_byte_identical_two_runs(tmp_path: Path) -> None:
    """Same draft → identical bytes (ADR-008 — Date/Message-ID/boundary fixed)."""
    kwargs = _kwargs(tmp_path)
    bundle = kwargs["pdf_bundle"]
    pdf_bytes = bundle.pdf_path.read_bytes()
    draft1 = build_email_draft(**kwargs)
    draft2 = build_email_draft(**kwargs)
    bytes_a = to_email_message(draft1, pdf_bytes=pdf_bytes).as_bytes()
    bytes_b = to_email_message(draft2, pdf_bytes=pdf_bytes).as_bytes()
    assert bytes_a == bytes_b


def test_override_to_overrides_student_email(tmp_path: Path) -> None:
    kwargs = _kwargs(tmp_path)
    kwargs["override_to"] = "operator@example.ac.kr"
    draft = build_email_draft(**kwargs)
    assert draft.to_header == "operator@example.ac.kr"
    # Student email is NOT used (US2 self-test FR-C05)
    assert draft.to_header != "student@example.com"
