"""confirm_gate.py unit tests (T059)."""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from immersio.email.composer import build_email_draft
from immersio.email.confirm_gate import ConfirmGateAborted, confirm_first_n
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


def _make_drafts(tmp_path: Path, n: int):
    drafts = []
    profile = _profile()
    for i in range(n):
        # Always 10 digits — pad i to 4 chars.
        sid = f"123456{i:04d}"
        pdf = tmp_path / f"{sid}_홍길동.pdf"
        pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF\n")
        bundle = StudentPDFBundle(
            student_id=sid,
            name_kr="홍길동",
            pdf_path=pdf,
            pdf_filename=pdf.name,
            pdf_size_bytes=pdf.stat().st_size,
            pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
            body_first_page_text_normalized=f"학번{sid}",
            body_contains_student_id=True,
        )
        entry = EmailMappingEntry(
            student_id=sid,
            email=f"student{i}@example.com",
            source_row_index=i,
            original_timestamp=datetime(2026, 5, 1, 9, 0, 0, tzinfo=UTC),
        )
        draft = build_email_draft(
            profile=profile,
            mapping_entry=entry,
            pdf_bundle=bundle,
            course_name_kr="인체구조와기능",
            course_slug="anatomy",
            semester="2026-1",
            exam_name="중간고사",
            sent_date=date(2026, 5, 1),
            mode=DispatchMode.PRODUCTION,
        )
        drafts.append((draft, bundle))
    return drafts


def test_yes_proceeds(tmp_path: Path) -> None:
    drafts = _make_drafts(tmp_path, 5)
    stdin = io.StringIO("yes\n")
    stdout = io.StringIO()
    confirm_first_n(drafts, sample_size=3, stdin=stdin, stdout=stdout)
    text = stdout.getvalue()
    assert "1234560000" in text
    assert "1234560002" in text


def test_no_aborts(tmp_path: Path) -> None:
    drafts = _make_drafts(tmp_path, 5)
    with pytest.raises(ConfirmGateAborted):
        confirm_first_n(drafts, sample_size=3, stdin=io.StringIO("no\n"))


def test_empty_input_aborts(tmp_path: Path) -> None:
    drafts = _make_drafts(tmp_path, 5)
    with pytest.raises(ConfirmGateAborted):
        confirm_first_n(drafts, sample_size=3, stdin=io.StringIO("\n"))


def test_y_lowercase_aborts(tmp_path: Path) -> None:
    """Strict ``yes`` only — single ``y`` rejected."""
    drafts = _make_drafts(tmp_path, 5)
    with pytest.raises(ConfirmGateAborted):
        confirm_first_n(drafts, sample_size=3, stdin=io.StringIO("y\n"))


def test_yes_uppercase_aborts(tmp_path: Path) -> None:
    """Strict case-sensitive — ``YES`` rejected."""
    drafts = _make_drafts(tmp_path, 5)
    with pytest.raises(ConfirmGateAborted):
        confirm_first_n(drafts, sample_size=3, stdin=io.StringIO("YES\n"))


def test_sample_size_zero_rejected(tmp_path: Path) -> None:
    drafts = _make_drafts(tmp_path, 5)
    with pytest.raises(ValueError):
        confirm_first_n(drafts, sample_size=0, stdin=io.StringIO("yes\n"))


def test_sample_size_above_ten_rejected(tmp_path: Path) -> None:
    drafts = _make_drafts(tmp_path, 12)
    with pytest.raises(ValueError):
        confirm_first_n(drafts, sample_size=11, stdin=io.StringIO("yes\n"))


def test_sample_size_one_proceeds(tmp_path: Path) -> None:
    drafts = _make_drafts(tmp_path, 5)
    stdout = io.StringIO()
    confirm_first_n(drafts, sample_size=1, stdin=io.StringIO("yes\n"), stdout=stdout)
    # Only first student appears
    text = stdout.getvalue()
    assert "1234560000" in text
    assert "1234560001" not in text
