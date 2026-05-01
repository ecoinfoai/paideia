"""Integration test — idempotent replay (T074, SC-006).

Pre-populates the dispatch log with N success rows, re-runs the
pipeline with default RetryMode, and asserts that those N students
are skipped (Gmail API send_one is NOT called for them).
"""

from __future__ import annotations

import argparse
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from immersio.email.log import append_dispatch_log_rows
from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))


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


class _CountingDispatcher:
    captured: list = []

    def __init__(self, profile):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def send_one(self, draft, *, pdf_bytes):
        from immersio.email.sender import SendResult

        type(self).captured.append(draft.student_id)
        return SendResult(
            status=DispatchStatus.SUCCESS,
            error_kind="",
            error_detail="",
            gmail_server_message_id=f"id-{draft.student_id}",
        )


def _seed_log(log_path: Path, sids: list[str], status: DispatchStatus) -> None:
    """Pre-populate the dispatch log with N rows of the given status."""
    rows = [
        DispatchLogRow(
            student_id=sid,
            name_kr="홍길동",
            email="ok@example.com",
            pdf_filename=f"{sid}_홍길동.pdf",
            pdf_sha256="a" * 64,
            attempt_at_kst=datetime(2026, 4, 30, 12, 0, 0, tzinfo=KST),
            mode=DispatchMode.PRODUCTION,
            status=status,
            smtp_message_id="<x@example.ac.kr>",
            error_kind="",
            error_detail="",
            exam_name="중간고사",
            cohort=CohortLabel.ALL,
        )
        for sid in sids
    ]
    append_dispatch_log_rows(log_path, rows)


def test_idempotent_replay_skips_prior_success(
    email_fixture, monkeypatch
) -> None:
    """SC-006: students with prior success log row are skipped on re-run."""
    # Pre-populate log: 2 of the 5 fixture students already success
    log_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    prior_success = [
        email_fixture["students"][0][0],  # 1234567001
        email_fixture["students"][1][0],  # 1234567002
    ]
    _seed_log(log_path, prior_success, DispatchStatus.SUCCESS)

    _CountingDispatcher.captured = []
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _CountingDispatcher
    )
    rc = run_email_dispatch(_args())
    assert rc == 0

    # Only the 3 non-prior-success students get sent
    assert len(_CountingDispatcher.captured) == 3
    for sid in prior_success:
        assert sid not in _CountingDispatcher.captured
