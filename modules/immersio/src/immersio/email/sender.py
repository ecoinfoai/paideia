"""Gmail API dispatcher (T055 — US2 self-test + US3 본 발송 wire-in).

``GmailAPIDispatcher`` is a context manager that builds a Gmail API
service via the validated SA credentials (``secrets.get_gmail_credentials``)
and dispatches one ``EmailMessageDraft`` at a time. HTTP error codes are
classified into ``DispatchStatus`` + ``error_kind`` per
contracts/email_mime_format.md §발송 모드.

This module is *not* imported by the dry-run path (Phase 3 US1) — the
contract test ``test_dry_run_no_send_call.py`` enforces zero
``messages().send(`` and ``import googleapiclient`` references in the
9 dry-run modules. Phase 4+ pipeline branches import this module
explicitly when ``--send`` is set.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass

from google.oauth2.service_account import Credentials  # ALLOW_HARDCODING: SA imports
from googleapiclient.discovery import build  # ALLOW_HARDCODING: live Gmail API
from googleapiclient.errors import HttpError  # ALLOW_HARDCODING: error classifier
from paideia_shared.schemas import (
    DispatchStatus,
    EmailMessageDraft,
    ProfessorProfile,
    TestProfile,
)

from .composer import to_email_message
from .secrets import get_gmail_credentials


@dataclass(frozen=True)
class SendResult:
    """Outcome of a single ``GmailAPIDispatcher.send_one`` call."""

    status: DispatchStatus
    error_kind: str
    error_detail: str
    gmail_server_message_id: str


def classify_gmail_api_error(exc: HttpError) -> tuple[DispatchStatus, str]:
    """Map an ``HttpError`` to ``(DispatchStatus, error_kind)`` pair.

    Args:
        exc: Caught ``googleapiclient.errors.HttpError`` from a send call.

    Returns:
        Tuple of (status, error_kind) per contracts/email_mime_format.md
        §"Gmail API 응답 분류" table.
    """
    code = exc.resp.status if hasattr(exc, "resp") and exc.resp is not None else 0
    content = ""
    try:
        content = exc.content.decode("utf-8", errors="replace") if exc.content else ""
    except (AttributeError, UnicodeDecodeError):
        content = str(exc)

    if code == 400:
        return DispatchStatus.FAILED, "gmail_api_invalid_recipient"
    if code == 401:
        return DispatchStatus.FAILED, "gmail_api_auth_failed"
    if code == 403:
        if "quota" in content.lower():
            return DispatchStatus.TEMPORARY_FAILURE, "gmail_api_quota_exceeded"
        return DispatchStatus.FAILED, "gmail_api_domain_policy"
    if code == 429:
        return DispatchStatus.TEMPORARY_FAILURE, "gmail_api_rate_limit"
    if code in (500, 502, 503, 504):
        return DispatchStatus.TEMPORARY_FAILURE, "gmail_api_server_error"
    return DispatchStatus.FAILED, "gmail_api_unknown"


def _mask_secrets(text: str) -> str:
    """Strip any embedded SA JSON / private key bytes from error messages."""
    if not text:
        return ""
    if "BEGIN PRIVATE KEY" in text or "private_key" in text.lower():
        return "<redacted: contained private key material>"
    return text[:200]


class GmailAPIDispatcher:
    """Context manager around the Gmail API service for single-message send.

    Rate limiting (US5 / FR-E01): when ``rate_per_minute`` is set,
    ``send_one`` sleeps ``60 / rate_per_minute`` seconds *after* each send
    so the per-minute throughput stays at or below the operator-configured
    limit. The caller is responsible for *not* applying the sleep on the
    final send (no successor needs spacing) — typically by counting the
    pending queue and skipping the sleep when 0.
    """

    def __init__(
        self,
        profile: ProfessorProfile | TestProfile,
        *,
        rate_per_minute: int | None = None,
    ) -> None:
        if not isinstance(profile, (ProfessorProfile, TestProfile)):
            raise TypeError(
                f"GmailAPIDispatcher: profile must be ProfessorProfile or "
                f"TestProfile, got {type(profile).__name__}"
            )
        if rate_per_minute is not None and (
            rate_per_minute < 1 or rate_per_minute > 30
        ):
            raise ValueError(
                f"GmailAPIDispatcher: rate_per_minute must be 1 ≤ N ≤ 30 "
                f"(got {rate_per_minute})"
            )
        self._profile = profile
        self._service = None
        self._creds: Credentials | None = None
        self._rate_per_minute = rate_per_minute

    def __enter__(self) -> GmailAPIDispatcher:
        self._creds = get_gmail_credentials(self._profile)
        self._service = build(
            "gmail",
            "v1",
            credentials=self._creds,
            cache_discovery=False,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._service = None
        self._creds = None

    def sleep_between_sends(self) -> None:
        """Apply rate-limit sleep between sends (US5 / FR-E01).

        Caller invokes this *after* a successful send and *before* the
        next ``send_one`` call. No-op when ``rate_per_minute`` was not
        configured. The caller is expected to skip this between the
        last send and EOF (no successor needs spacing).
        """
        if self._rate_per_minute is None:
            return
        time.sleep(60.0 / self._rate_per_minute)

    def send_one(
        self, draft: EmailMessageDraft, *, pdf_bytes: bytes
    ) -> SendResult:
        """Send a single ``EmailMessageDraft`` via the Gmail API."""
        if self._service is None:
            raise RuntimeError(
                "GmailAPIDispatcher: send_one called outside context manager"
            )

        msg = to_email_message(draft, pdf_bytes=pdf_bytes)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        body = {"raw": raw}

        try:
            request = self._service.users().messages().send(
                userId="me", body=body
            )
            response = request.execute()
        except HttpError as exc:
            status, error_kind = classify_gmail_api_error(exc)
            return SendResult(
                status=status,
                error_kind=error_kind,
                error_detail=_mask_secrets(str(exc)),
                gmail_server_message_id="",
            )
        except (TimeoutError, OSError) as exc:
            return SendResult(
                status=DispatchStatus.TEMPORARY_FAILURE,
                error_kind="network_timeout",
                error_detail=_mask_secrets(str(exc)),
                gmail_server_message_id="",
            )

        gmail_id = response.get("id", "")
        if not gmail_id:
            return SendResult(
                status=DispatchStatus.FAILED,
                error_kind="gmail_api_unknown",
                error_detail="response missing 'id' field",
                gmail_server_message_id="",
            )
        return SendResult(
            status=DispatchStatus.SUCCESS,
            error_kind="",
            error_detail="",
            gmail_server_message_id=gmail_id,
        )


__all__ = [
    "GmailAPIDispatcher",
    "SendResult",
    "classify_gmail_api_error",
]
