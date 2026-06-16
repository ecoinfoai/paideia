"""Contract tests for EmailMessageDraft (T013).

The single-recipient validator on ``to_header`` is the load-bearing
guard against silent multi-recipient sends (FR-C03).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from paideia_shared.schemas import DispatchMode, EmailMessageDraft
from pydantic import ValidationError


def _valid_kwargs() -> dict:
    return dict(
        student_id="1234567890",
        name_kr="홍길동",
        from_header="인체구조와기능 (정광석 교수) <noreply@example.ac.kr>",
        reply_to_header="정광석 <kjeong@example.ac.kr>",
        to_header="student@example.com",
        subject="중간고사 결과 안내",
        subject_encoded="=?UTF-8?B?...?=",
        body_text="본문 내용",
        attachment_filename="1234567890_홍길동.pdf",
        attachment_sha256="a" * 64,
        attachment_bytes_size=1024,
        date_header=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        message_id="<deterministic@example.ac.kr>",
        mime_boundary="===PAIDEIA_BOUNDARY_001===",
        mode=DispatchMode.PRODUCTION,
    )


def test_valid_draft_construction() -> None:
    d = EmailMessageDraft(**_valid_kwargs())
    assert d.to_header == "student@example.com"


def test_to_header_rejects_comma_separator() -> None:
    kwargs = _valid_kwargs()
    kwargs["to_header"] = "a@example.com, b@example.com"
    with pytest.raises(ValidationError) as exc_info:
        EmailMessageDraft(**kwargs)
    assert "single recipient" in str(exc_info.value)


def test_to_header_rejects_semicolon_separator() -> None:
    kwargs = _valid_kwargs()
    kwargs["to_header"] = "a@example.com; b@example.com"
    with pytest.raises(ValidationError):
        EmailMessageDraft(**kwargs)


def test_attachment_sha256_must_be_hex64() -> None:
    kwargs = _valid_kwargs()
    kwargs["attachment_sha256"] = "g" * 64  # 'g' not hex
    with pytest.raises(ValidationError):
        EmailMessageDraft(**kwargs)


def test_message_id_must_have_brackets() -> None:
    kwargs = _valid_kwargs()
    kwargs["message_id"] = "no-brackets@example.com"
    with pytest.raises(ValidationError):
        EmailMessageDraft(**kwargs)


def test_attachment_size_must_be_positive() -> None:
    kwargs = _valid_kwargs()
    kwargs["attachment_bytes_size"] = 0
    with pytest.raises(ValidationError):
        EmailMessageDraft(**kwargs)


def test_student_id_must_be_ten_digits() -> None:
    kwargs = _valid_kwargs()
    kwargs["student_id"] = "123"
    with pytest.raises(ValidationError):
        EmailMessageDraft(**kwargs)


def test_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["extra"] = "leak"
    with pytest.raises(ValidationError):
        EmailMessageDraft(**kwargs)
