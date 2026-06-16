"""TestProfile + DummyStudent — test-mode profile YAML model (data-model.md §1.2).

Discriminated union with ProfessorProfile via ``profile_kind``. Adds 3
test-only fields (``recipient_pool``, ``dummy_fixture_dir``,
``dummy_students``) on top of the operator schema.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    DirectoryPath,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from .professor_profile import (
    _PROFILE_NAME_RE,
    _Booking,
    _GmailApi,
    _Institution,
    _OperationalDefaults,
    _SecretsRef,
    _SendAccount,
    _Sender,
)

_STUDENT_ID_RE = re.compile(r"^\d{10}$")


class DummyStudent(BaseModel):
    """One row of ``test_profile.dummy_students`` (TC-007)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    student_id: str
    name_kr: str = Field(min_length=1)

    @field_validator("student_id")
    @classmethod
    def _v_student_id(cls, value: str) -> str:
        if not _STUDENT_ID_RE.fullmatch(value):
            raise ValueError(f"DummyStudent.student_id must match ^\\d{{10}}$ (got {value!r})")
        return value


class TestProfile(BaseModel):
    """Test-mode profile: operator schema + recipient pool + dummy fixtures.

    Emits to the test gold subdirectory (``_test/``) and never touches
    the production roster or PDF directory (TC-004).
    """

    __test__ = False  # disable pytest collection for this Pydantic model

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    profile_kind: Literal["test"]
    profile_name: str
    sender: _Sender
    send_account: _SendAccount
    institution: _Institution
    booking: _Booking
    gmail_api: _GmailApi
    secrets_ref: _SecretsRef
    operational_defaults: _OperationalDefaults
    recipient_pool: list[EmailStr] = Field(min_length=1, max_length=10)
    dummy_fixture_dir: DirectoryPath
    dummy_students: list[DummyStudent] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def _v_profile_name(self) -> Self:
        if not _PROFILE_NAME_RE.fullmatch(self.profile_name):
            raise ValueError(
                f"profile_name must match ^[a-z][a-z0-9-]{{1,30}}$ (got {self.profile_name!r})"
            )
        return self

    @model_validator(mode="after")
    def _v_subject_matches_send_account(self) -> Self:
        if self.gmail_api.service_account_subject != self.send_account.email:
            raise ValueError(
                f"gmail_api.service_account_subject "
                f"({self.gmail_api.service_account_subject!r}) must equal "
                f"send_account.email ({self.send_account.email!r})"
            )
        return self

    @model_validator(mode="after")
    def _v_recipient_pool_unique(self) -> Self:
        seen: set[str] = set()
        for addr in self.recipient_pool:
            if addr in seen:
                raise ValueError(f"recipient_pool contains duplicate address {addr!r}")
            seen.add(addr)
        return self

    @model_validator(mode="after")
    def _v_pool_dummy_length_match(self) -> Self:
        if len(self.recipient_pool) != len(self.dummy_students):
            raise ValueError(
                f"len(recipient_pool)={len(self.recipient_pool)} must equal "
                f"len(dummy_students)={len(self.dummy_students)} — TC-003 "
                f"requires 1:1 matching for test mode"
            )
        return self

    @model_validator(mode="after")
    def _v_dummy_students_unique(self) -> Self:
        ids = [s.student_id for s in self.dummy_students]
        if len(set(ids)) != len(ids):
            raise ValueError("dummy_students.student_id values must be unique")
        return self

    @model_validator(mode="after")
    def _v_dummy_fixture_dir_absolute(self) -> Self:
        path = Path(str(self.dummy_fixture_dir))
        if not path.is_absolute():
            raise ValueError(
                f"dummy_fixture_dir must be absolute path (got {self.dummy_fixture_dir!r})"
            )
        return self


__all__ = ["DummyStudent", "TestProfile"]
