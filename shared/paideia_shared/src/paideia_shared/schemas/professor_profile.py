"""ProfessorProfile — operator profile YAML model (data-model.md §1).

Discriminated union with TestProfile via ``profile_kind``. Loaded by
``immersio.email.profile.ProfileLoader`` from
``~/.config/paideia/immersio_email/profiles/<NAME>.yaml`` (FR-G08).
"""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    model_validator,
)

_PROFILE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
_ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
_GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class _Sender(BaseModel):
    """Reply-To target — the *professor* (not the send account)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    display_name: str = Field(min_length=1, max_length=50)
    email: EmailStr


class _SendAccount(BaseModel):
    """From-header email — dedicated send-only mailbox (FR-B07)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    email: EmailStr


class _Institution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    university_name: str = Field(min_length=1)
    department_name: str = Field(min_length=1)


class _Booking(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    google_calendar_url: HttpUrl

    @model_validator(mode="after")
    def _v_calendar_host(self) -> Self:
        host = self.google_calendar_url.host or ""
        # Google publishes appointment URLs under two distinct hosts:
        # - calendar.google.com — long form (/calendar/u/0/appointments/AcZssZ...)
        # - calendar.app.google — short share URL (e.g. /PXSBa7JhMqKssi846)
        # Both are first-party Google. Reject anything else.
        allowed_hosts = ("calendar.google.com", "calendar.app.google")
        if host not in allowed_hosts:
            raise ValueError(
                f"booking.google_calendar_url host must be one of {allowed_hosts} (got {host!r})"
            )
        return self


class _GmailApi(BaseModel):
    """Gmail API + Domain-Wide Delegation impersonation target."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    service_account_subject: EmailStr
    scopes: list[Literal["https://www.googleapis.com/auth/gmail.send"]] = Field(
        min_length=1, max_length=1
    )

    @model_validator(mode="after")
    def _v_scopes(self) -> Self:
        if list(self.scopes) != [_GMAIL_SEND_SCOPE]:
            raise ValueError(
                f"gmail_api.scopes must be exactly [{_GMAIL_SEND_SCOPE!r}] (got {self.scopes!r})"
            )
        return self


class _SecretsRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    service_account_json_path_env: str

    @model_validator(mode="after")
    def _v_env_var(self) -> Self:
        if not _ENV_VAR_RE.fullmatch(self.service_account_json_path_env):
            raise ValueError(
                f"secrets_ref.service_account_json_path_env must match "
                f"^[A-Z][A-Z0-9_]+$ (got {self.service_account_json_path_env!r})"
            )
        return self


class _OperationalDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rate_per_minute: int = Field(ge=1, le=30)
    confirm_sample_size: int = Field(ge=1, le=10)
    attachment_max_bytes: int = Field(ge=1024, le=209715200)


class ProfessorProfile(BaseModel):
    """Operator profile — the professor's send configuration.

    All required fields are immutable post-load (frozen=True). Validators:
    1. ``service_account_subject == send_account.email`` — DwD impersonation
       must target the explicit send account (FR-G02).
    2. ``gmail_api.scopes`` exactly ``[gmail.send]`` — least privilege
       (clarification 2026-05-01).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    profile_kind: Literal["operator"]
    profile_name: str
    sender: _Sender
    send_account: _SendAccount
    institution: _Institution
    booking: _Booking
    gmail_api: _GmailApi
    secrets_ref: _SecretsRef
    operational_defaults: _OperationalDefaults

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
                f"send_account.email ({self.send_account.email!r}) — "
                f"DwD impersonation target must match the explicit send account"
            )
        return self


__all__ = ["ProfessorProfile"]
