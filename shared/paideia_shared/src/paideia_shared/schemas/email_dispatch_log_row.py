"""DispatchLogRow + DispatchStatus + DispatchMode + CohortLabel — spec 006.

The append-only CSV row written to ``메일_발송로그.csv`` after each send
attempt (FR-D01). Column order is fixed (contracts/email_log_csv.md §13
columns) so direct ``csv.DictWriter`` round-trips are byte-identical
across re-runs.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, TypeAdapter, field_validator

_EMAIL_VALIDATOR = TypeAdapter(EmailStr)

_STUDENT_ID_RE = re.compile(r"^\d{10}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_MESSAGE_ID_RE = re.compile(r"^<[^@>]+@[^@>]+>$")


class DispatchStatus(StrEnum):
    """Canonical send-attempt status values (FR-D08 — 6 enum)."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"
    TEMPORARY_FAILURE = "temporary_failure"
    DRY_RUN = "dry_run"
    TEST_DUMMY = "test_dummy"


class DispatchMode(StrEnum):
    """Run-mode discriminator (FR-D09 — 2 enum)."""

    PRODUCTION = "production"
    TEST = "test"


class CohortLabel(StrEnum):
    """US6 cohort partition label (FR-H06 — 3 enum)."""

    LOW_SCORE = "low_score"
    REST = "rest"
    ALL = "all"


_VALID_ERROR_KINDS: frozenset[str] = frozenset({
    "",
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
})


class DispatchLogRow(BaseModel):
    """One row of the append-only ``메일_발송로그.csv`` file (FR-D01).

    Column order is locked to contracts/email_log_csv.md §13 columns so
    ``model_dump()`` -> ``csv.DictWriter`` round-trips deterministically
    even across Python dict-order quirks.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    COLUMN_ORDER: ClassVar[tuple[str, ...]] = (
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

    student_id: str
    name_kr: str
    email: str
    pdf_filename: str
    pdf_sha256: str
    attempt_at_kst: datetime
    mode: DispatchMode
    status: DispatchStatus
    smtp_message_id: str
    error_kind: str
    error_detail: str
    exam_name: str
    cohort: CohortLabel

    @field_validator("student_id")
    @classmethod
    def _v_student_id(cls, value: str) -> str:
        if not _STUDENT_ID_RE.fullmatch(value):
            raise ValueError(
                f"DispatchLogRow.student_id must match ^\\d{{10}}$ (got {value!r})"
            )
        return value

    @field_validator("name_kr")
    @classmethod
    def _v_name_kr(cls, value: str) -> str:
        if not value:
            raise ValueError("DispatchLogRow.name_kr must be non-empty")
        return value

    @field_validator("email")
    @classmethod
    def _v_email(cls, value: str) -> str:
        if value == "":
            return value
        _EMAIL_VALIDATOR.validate_python(value)
        return value

    @field_validator("pdf_sha256")
    @classmethod
    def _v_pdf_sha256(cls, value: str) -> str:
        if value == "":
            return value
        if not _HEX64_RE.fullmatch(value):
            raise ValueError(
                f"DispatchLogRow.pdf_sha256 must be hex64 or '' (got {value!r})"
            )
        return value

    @field_validator("smtp_message_id")
    @classmethod
    def _v_smtp_message_id(cls, value: str) -> str:
        if value == "":
            return value
        if not _MESSAGE_ID_RE.fullmatch(value):
            raise ValueError(
                f"DispatchLogRow.smtp_message_id must be RFC 5322 Message-ID "
                f"or '' (got {value!r})"
            )
        return value

    @field_validator("error_kind")
    @classmethod
    def _v_error_kind(cls, value: str) -> str:
        if value not in _VALID_ERROR_KINDS:
            raise ValueError(
                f"DispatchLogRow.error_kind {value!r} not in {_VALID_ERROR_KINDS}"
            )
        return value

    @field_validator("error_detail")
    @classmethod
    def _v_error_detail(cls, value: str) -> str:
        if len(value) > 200:
            raise ValueError(
                f"DispatchLogRow.error_detail max length 200 (got {len(value)})"
            )
        return value

    @field_validator("exam_name")
    @classmethod
    def _v_exam_name(cls, value: str) -> str:
        if not value:
            raise ValueError("DispatchLogRow.exam_name must be non-empty")
        return value


__all__ = [
    "DispatchStatus",
    "DispatchMode",
    "CohortLabel",
    "DispatchLogRow",
]
