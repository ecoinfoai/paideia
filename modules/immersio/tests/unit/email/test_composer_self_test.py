"""Composer self-test mode tests (T050)."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from immersio.email.composer import build_email_draft
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


def _make_kwargs(tmp_path: Path):
    pdf = tmp_path / "1234567001_홍길동.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF\n")
    return dict(
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
    )


def test_self_test_overrides_to_operator(tmp_path: Path) -> None:
    """FR-C05: override_to → To 헤더 = operator email, student email unused."""
    kwargs = _make_kwargs(tmp_path)
    kwargs["override_to"] = "alpha@example.ac.kr"  # operator's own
    draft = build_email_draft(**kwargs)
    assert draft.to_header == "alpha@example.ac.kr"
    # Student email NEVER appears
    assert "student@example.com" not in draft.to_header
    assert "student@example.com" not in draft.from_header
    assert "student@example.com" not in draft.reply_to_header


def test_self_test_body_keeps_student_id(tmp_path: Path) -> None:
    """Body still references the student's id/name (FR-C05 — same as student mode)."""
    kwargs = _make_kwargs(tmp_path)
    kwargs["override_to"] = "alpha@example.ac.kr"
    draft = build_email_draft(**kwargs)
    assert "홍길동" in draft.subject
    assert "1234567001" in draft.subject
    assert "1234567001" in draft.attachment_filename


def test_self_test_from_reply_to_unchanged(tmp_path: Path) -> None:
    """Self-test does NOT alter From / Reply-To headers (FR-C05 same shape)."""
    kwargs = _make_kwargs(tmp_path)
    student_draft = build_email_draft(**kwargs)
    kwargs["override_to"] = "alpha@example.ac.kr"
    self_test_draft = build_email_draft(**kwargs)
    assert student_draft.from_header == self_test_draft.from_header
    assert student_draft.reply_to_header == self_test_draft.reply_to_header


def test_no_override_to_uses_student_email(tmp_path: Path) -> None:
    """Default behavior unchanged when override_to is None."""
    kwargs = _make_kwargs(tmp_path)
    draft = build_email_draft(**kwargs)
    assert draft.to_header == "student@example.com"
