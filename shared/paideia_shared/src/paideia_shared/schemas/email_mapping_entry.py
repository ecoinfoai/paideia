"""EmailMappingEntry — student_id → email mapping row (data-model.md §1.3)."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_STUDENT_ID_RE = re.compile(r"^\d{10}$")


class EmailMappingEntry(BaseModel):
    """One Bronze CSV response → ``student_id → email`` mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    student_id: str
    email: EmailStr
    source_row_index: int = Field(ge=0)
    original_timestamp: datetime

    @field_validator("student_id")
    @classmethod
    def _v_student_id(cls, value: str) -> str:
        if not _STUDENT_ID_RE.fullmatch(value):
            raise ValueError(
                f"EmailMappingEntry.student_id must match ^\\d{{10}}$ "
                f"(got {value!r})"
            )
        return value

    @field_validator("email", mode="before")
    @classmethod
    def _v_email_lowercase(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


__all__ = ["EmailMappingEntry"]
