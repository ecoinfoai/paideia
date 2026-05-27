"""Integration test — self-test mode sends only to operator (T052)."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import DispatchStatus


def _args(self_test: int = 5) -> argparse.Namespace:
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=True,
        self_test=self_test,
        retry_failed=False,
        retry_skipped=False,
        rate_per_min=None,
        cohort="all",
        confirm_sample=None,
        bronze_csv=None,
        gold_pdf_dir=None,
        silver_master=None,
        silver_student_metrics=None,
        quiet=False,
        verbose=False,
    )
    args._stdin = io.StringIO("yes\n")
    return args


def test_self_test_sends_to_operator_only(email_fixture, monkeypatch) -> None:
    """FR-C05: 5 self-test sends → all To headers = operator email."""
    captured_drafts = []

    class _FakeDispatcher:
        def __init__(self, profile, **kwargs):
            self.profile = profile

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def send_one(self, draft, *, pdf_bytes):
            captured_drafts.append(draft)
            from immersio.email.sender import SendResult

            return SendResult(
                status=DispatchStatus.SUCCESS,
                error_kind="",
                error_detail="",
                gmail_server_message_id=f"id-{draft.student_id}",
            )

    monkeypatch.setattr("immersio.email.sender.GmailAPIDispatcher", _FakeDispatcher)

    rc = run_email_dispatch(_args(self_test=5))
    assert rc == 0
    assert len(captured_drafts) == 5

    # FR-C05: every To header is the operator's own email.
    for draft in captured_drafts:
        assert draft.to_header == "alpha@example.ac.kr"
    # Student emails MUST NOT appear in any send.
    student_emails = {s[2] for s in email_fixture["students"]}
    for draft in captured_drafts:
        assert draft.to_header not in student_emails


def test_self_test_log_status_is_test_dummy(email_fixture, monkeypatch) -> None:
    """Self-test → log status = test_dummy (FR-D08), not success."""

    class _FakeDispatcher:
        def __init__(self, profile, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def send_one(self, draft, *, pdf_bytes):
            from immersio.email.sender import SendResult

            return SendResult(
                status=DispatchStatus.SUCCESS,
                error_kind="",
                error_detail="",
                gmail_server_message_id=f"id-{draft.student_id}",
            )

    monkeypatch.setattr("immersio.email.sender.GmailAPIDispatcher", _FakeDispatcher)

    rc = run_email_dispatch(_args(self_test=3))
    assert rc == 0

    csv_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    text = csv_path.read_text(encoding="utf-8")
    # 3 rows of test_dummy + 2 rows of original DRY_RUN converted? Actually
    # in self-test mode, the first 3 are sent; other 2 are still in
    # log_rows as initial DRY_RUN/SUCCESS placeholders that were not
    # touched. Verify the test_dummy count is exactly 3.
    assert text.count(",test_dummy,") == 3


def test_self_test_n_zero_rejected(email_fixture) -> None:
    """N=0 should be rejected (CLI validation also catches this)."""
    rc = run_email_dispatch(_args(self_test=0))
    assert rc == 2


def test_self_test_n_too_large_rejected(email_fixture) -> None:
    """N=11 exceeds the 1≤N≤10 contract."""
    rc = run_email_dispatch(_args(self_test=11))
    assert rc == 2
