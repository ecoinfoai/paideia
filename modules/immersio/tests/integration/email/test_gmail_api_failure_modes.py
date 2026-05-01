"""Integration test — Gmail API failure modes propagate to log + exit (T065)."""

from __future__ import annotations

import argparse
import io
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from immersio.email.pipeline import run_email_dispatch
from immersio.email.sender import SendResult
from paideia_shared.schemas import DispatchStatus


def _args() -> argparse.Namespace:
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=True,
        self_test=None,
        retry_failed=False,
        retry_skipped=False,
        rate_per_min=None,
        cohort="all",
        confirm_sample=3,
        bronze_csv=None,
        gold_pdf_dir=None,
        silver_master=None,
        silver_student_metrics=None,
        quiet=False,
        verbose=False,
    )
    args._stdin = io.StringIO("yes\n")
    args._stdout = io.StringIO()
    return args


class _SequencedDispatcher:
    """Returns SendResults in scripted order — first auth-fail aborts entire run."""

    sequence: list[SendResult] = []
    captured: list = []

    def __init__(self, profile, **kwargs):
        type(self).captured = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def send_one(self, draft, *, pdf_bytes):
        type(self).captured.append(draft)
        idx = len(type(self).captured) - 1
        if idx < len(type(self).sequence):
            return type(self).sequence[idx]
        return SendResult(
            status=DispatchStatus.SUCCESS,
            error_kind="",
            error_detail="",
            gmail_server_message_id=f"id-{draft.student_id}",
        )


def test_mixed_responses_recorded_correctly(
    email_fixture, monkeypatch
) -> None:
    """200, 429, 400, 200, 200 → 3 success + 1 temporary + 1 failed."""
    _SequencedDispatcher.sequence = [
        SendResult(DispatchStatus.SUCCESS, "", "", "id-1"),
        SendResult(
            DispatchStatus.TEMPORARY_FAILURE,
            "gmail_api_rate_limit",
            "429 rate limit",
            "",
        ),
        SendResult(
            DispatchStatus.FAILED,
            "gmail_api_invalid_recipient",
            "400 invalid To",
            "",
        ),
        SendResult(DispatchStatus.SUCCESS, "", "", "id-4"),
        SendResult(DispatchStatus.SUCCESS, "", "", "id-5"),
    ]
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _SequencedDispatcher
    )
    rc = run_email_dispatch(_args())
    # 1 failed → exit 8 (partial failure)
    assert rc == 8

    csv_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    text = csv_path.read_text(encoding="utf-8")
    assert text.count(",success,") == 3
    assert text.count(",temporary_failure,") == 1
    assert text.count(",failed,") == 1


def test_401_invalid_grant_aborts_with_exit_5(email_fixture, monkeypatch) -> None:
    """401 → immediate abort with exit 5; subsequent students not sent."""
    _SequencedDispatcher.sequence = [
        SendResult(DispatchStatus.SUCCESS, "", "", "id-1"),
        SendResult(
            DispatchStatus.FAILED,
            "gmail_api_auth_failed",
            "401 invalid_grant",
            "",
        ),
    ]
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _SequencedDispatcher
    )
    rc = run_email_dispatch(_args())
    assert rc == 5
    # Only 2 send_one calls (1 success + 1 auth-fail) — students #3-5 not sent.
    assert len(_SequencedDispatcher.captured) == 2
