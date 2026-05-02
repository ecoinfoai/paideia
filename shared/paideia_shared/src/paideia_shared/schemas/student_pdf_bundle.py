"""StudentPDFBundle — per-student PDF metadata (data-model.md §1.4)."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, FilePath, field_validator

_STUDENT_ID_RE = re.compile(r"^\d{10}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class StudentPDFBundle(BaseModel):
    """Metadata for one ``{학번}_{이름}.pdf`` attachment."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    student_id: str
    name_kr: str = Field(min_length=1)
    pdf_path: FilePath
    pdf_filename: str
    pdf_size_bytes: int = Field(gt=0)
    pdf_sha256: str
    body_first_page_text_normalized: str
    body_contains_student_id: bool

    @field_validator("student_id")
    @classmethod
    def _v_student_id(cls, value: str) -> str:
        if not _STUDENT_ID_RE.fullmatch(value):
            raise ValueError(
                f"StudentPDFBundle.student_id must match ^\\d{{10}}$ "
                f"(got {value!r})"
            )
        return value

    @field_validator("pdf_filename")
    @classmethod
    def _v_filename_basename(cls, value: str) -> str:
        if value != Path(value).name:
            raise ValueError(
                f"StudentPDFBundle.pdf_filename must be basename only "
                f"(got {value!r})"
            )
        return value

    @field_validator("pdf_sha256")
    @classmethod
    def _v_pdf_sha256(cls, value: str) -> str:
        if not _HEX64_RE.fullmatch(value):
            raise ValueError(
                f"StudentPDFBundle.pdf_sha256 must be hex64 (got {value!r})"
            )
        return value


__all__ = ["StudentPDFBundle"]
