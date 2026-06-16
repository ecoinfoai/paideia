"""Contract tests for EmailMappingEntry (T009)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from paideia_shared.schemas import EmailMappingEntry
from pydantic import ValidationError


def test_valid_entry_construction() -> None:
    entry = EmailMappingEntry(
        student_id="2026194999",
        email="STUDENT@EXAMPLE.COM",
        source_row_index=0,
        original_timestamp=datetime(2026, 5, 1, 9, 0, 0, tzinfo=UTC),
    )
    assert entry.student_id == "2026194999"
    assert entry.email == "student@example.com"  # lowercase normalized


def test_email_lowercase_normalization() -> None:
    entry = EmailMappingEntry(
        student_id="1234567890",
        email="  Mixed.Case@EXAMPLE.COM  ",  # whitespace + mixed case
        source_row_index=5,
        original_timestamp=datetime.now(tz=UTC),
    )
    assert entry.email == "mixed.case@example.com"


def test_student_id_must_be_ten_digits() -> None:
    with pytest.raises(ValidationError):
        EmailMappingEntry(
            student_id="123456789",  # 9 digits
            email="ok@example.com",
            source_row_index=0,
            original_timestamp=datetime.now(tz=UTC),
        )


def test_invalid_email_rejected() -> None:
    with pytest.raises(ValidationError):
        EmailMappingEntry(
            student_id="1234567890",
            email="not-an-email",
            source_row_index=0,
            original_timestamp=datetime.now(tz=UTC),
        )


def test_source_row_index_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        EmailMappingEntry(
            student_id="1234567890",
            email="ok@example.com",
            source_row_index=-1,
            original_timestamp=datetime.now(tz=UTC),
        )


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        EmailMappingEntry(
            student_id="1234567890",
            email="ok@example.com",
            source_row_index=0,
            original_timestamp=datetime.now(tz=UTC),
            extra_field="leak",
        )
