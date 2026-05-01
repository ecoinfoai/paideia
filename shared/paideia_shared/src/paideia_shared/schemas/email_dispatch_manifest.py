"""EmailManifest — dispatch run manifest (data-model.md §1.6).

Constitution V "부분 산출 금지" — every immersio-email run writes a
manifest.json summarising inputs, outputs, and per-status counts. No
secrets land in the manifest: only the env-var *name* is recorded
(FR-G02), never the value or the JSON file contents.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .email_dispatch_log_row import DispatchMode

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SEMESTER_RE = re.compile(r"^\d{4}-[12SW]$")
_COURSE_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_PROFILE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


class EmailManifestInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bronze_csv_path: str
    bronze_csv_sha256: str
    gold_pdf_dir_path: str
    gold_pdf_count: int = Field(ge=0)
    silver_master_path: str
    silver_master_sha256: str

    @field_validator("bronze_csv_sha256", "silver_master_sha256")
    @classmethod
    def _v_sha256(cls, value: str) -> str:
        if not _HEX64_RE.fullmatch(value):
            raise ValueError(
                f"manifest input sha256 must be hex64 (got {value!r})"
            )
        return value


class EmailManifestOutputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    silver_mapping_path: str
    silver_mapping_rows: int = Field(ge=0)
    dispatch_log_path: str
    report_md_path: str
    preview_dir_path: str = ""


class EmailManifestCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    success: int = Field(ge=0)
    skipped: int = Field(ge=0)
    failed: int = Field(ge=0)
    temporary_failure: int = Field(ge=0)
    dry_run: int = Field(ge=0)
    test_dummy: int = Field(ge=0)


class EmailManifest(BaseModel):
    """Per-run manifest written to ``manifest_email.json`` (FR-D06).

    Secrets policy: no field stores the *value* of the SA JSON path env
    var or the JSON file contents — only the env-var *name* lives in
    ``profile_secrets_ref_env_var_name``. The Service Account
    client_email is also excluded entirely.
    """  # ALLOW_HARDCODING: docstring meta-mention of the excluded SA domain pattern

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: str = "1.0.0"
    semester: str
    course_slug: str
    course_name_kr: str = Field(min_length=1)
    exam_name: str = Field(min_length=1)
    sent_date_kst: date
    mode: DispatchMode
    profile_name: str
    profile_kind: Literal["operator", "test"]
    profile_secrets_ref_env_var_name: str
    inputs: EmailManifestInputs
    outputs: EmailManifestOutputs
    counts: EmailManifestCounts
    ruleset_version: str = "immersio-email-v0.1.0"
    tool_version: str
    started_at_kst: datetime
    completed_at_kst: datetime

    @field_validator("semester")
    @classmethod
    def _v_semester(cls, value: str) -> str:
        if not _SEMESTER_RE.fullmatch(value):
            raise ValueError(f"semester must match ^\\d{{4}}-[12SW]$ (got {value!r})")
        return value

    @field_validator("course_slug")
    @classmethod
    def _v_course_slug(cls, value: str) -> str:
        if not _COURSE_SLUG_RE.fullmatch(value):
            raise ValueError(
                f"course_slug must match ^[a-z][a-z0-9-]{{1,39}}$ (got {value!r})"
            )
        return value

    @field_validator("profile_name")
    @classmethod
    def _v_profile_name(cls, value: str) -> str:
        if not _PROFILE_NAME_RE.fullmatch(value):
            raise ValueError(
                f"profile_name must match ^[a-z][a-z0-9-]{{1,30}}$ "
                f"(got {value!r})"
            )
        return value


__all__ = [
    "EmailManifest",
    "EmailManifestInputs",
    "EmailManifestOutputs",
    "EmailManifestCounts",
]
