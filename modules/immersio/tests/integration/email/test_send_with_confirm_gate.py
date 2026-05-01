"""Integration test — confirm gate gates production send (T064)."""

from __future__ import annotations

import argparse

import pytest

from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import DispatchStatus


def _args(*, send: bool, confirm_input: str = "yes\n") -> argparse.Namespace:
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=send,
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
    # Stash a stdin object on args so confirm_gate uses it instead of sys.stdin.
    import io as _io
    args._stdin = _io.StringIO(confirm_input)
    args._stdout = _io.StringIO()
    return args


class _CapturingDispatcher:
    captured: list = []

    def __init__(self, profile, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def send_one(self, draft, *, pdf_bytes):
        from immersio.email.sender import SendResult

        type(self).captured.append(draft)
        return SendResult(
            status=DispatchStatus.SUCCESS,
            error_kind="",
            error_detail="",
            gmail_server_message_id=f"id-{draft.student_id}",
        )


def test_no_aborts_send_with_zero_calls(email_fixture, monkeypatch) -> None:
    """SC-004: 'no' at the gate → 0 send calls + exit 0 (safe abort)."""
    _CapturingDispatcher.captured = []
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _CapturingDispatcher
    )
    rc = run_email_dispatch(_args(send=True, confirm_input="no\n"))
    assert rc == 0
    assert len(_CapturingDispatcher.captured) == 0


def test_yes_proceeds_to_send(email_fixture, monkeypatch) -> None:
    """'yes' → all 5 fixture students sent."""
    _CapturingDispatcher.captured = []
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _CapturingDispatcher
    )
    rc = run_email_dispatch(_args(send=True, confirm_input="yes\n"))
    assert rc == 0
    assert len(_CapturingDispatcher.captured) == 5
