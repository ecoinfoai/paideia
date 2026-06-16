"""EmailMessageDraft — pre-send MIME draft (data-model.md §1.8).

Validators enforce single-recipient (FR-C03) and deterministic Message-ID
(R2) so byte-identical .eml output is preserved across re-runs.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .email_dispatch_log_row import DispatchMode

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_MESSAGE_ID_RE = re.compile(r"^<[^@>]+@[^@>]+>$")
_STUDENT_ID_RE = re.compile(r"^\d{10}$")


class EmailMessageDraft(BaseModel):
    """Validated MIME bundle ready for send or .eml preview.

    ``to_header`` is single-recipient only — comma- or semicolon-
    separated addresses are rejected to prevent silent multi-recipient
    sends (FR-C03).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_id: str
    name_kr: str = Field(min_length=1)
    from_header: str = Field(min_length=1)
    reply_to_header: str = Field(min_length=1)
    to_header: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    subject_encoded: str = Field(min_length=1)
    body_text: str = Field(min_length=1)
    attachment_filename: str = Field(min_length=1)
    attachment_sha256: str
    attachment_bytes_size: int = Field(gt=0)
    date_header: datetime
    message_id: str
    mime_boundary: str = Field(min_length=1)
    mode: DispatchMode

    @field_validator("student_id")
    @classmethod
    def _v_student_id(cls, value: str) -> str:
        if not _STUDENT_ID_RE.fullmatch(value):
            raise ValueError(f"EmailMessageDraft.student_id must match ^\\d{{10}}$ (got {value!r})")
        return value

    @field_validator("to_header")
    @classmethod
    def _v_to_header_single(cls, value: str) -> str:
        if "," in value or ";" in value:
            raise ValueError(
                f"EmailMessageDraft.to_header must be a single recipient — "
                f"comma/semicolon separator detected (got {value!r}). "
                f"Multi-recipient sends are blocked by FR-C03."
            )
        return value

    @field_validator("attachment_sha256")
    @classmethod
    def _v_attachment_sha256(cls, value: str) -> str:
        if not _HEX64_RE.fullmatch(value):
            raise ValueError(f"EmailMessageDraft.attachment_sha256 must be hex64 (got {value!r})")
        return value

    @field_validator("message_id")
    @classmethod
    def _v_message_id(cls, value: str) -> str:
        if not _MESSAGE_ID_RE.fullmatch(value):
            raise ValueError(
                f"EmailMessageDraft.message_id must be RFC 5322 Message-ID (got {value!r})"
            )
        return value


__all__ = ["EmailMessageDraft"]
