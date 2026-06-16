"""Integration test — --retry-failed only re-tries failed/temporary (T075)."""

from __future__ import annotations

import argparse
import io
from datetime import datetime, timedelta, timezone

from immersio.email.log import append_dispatch_log_rows
from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))


def _args(*, retry_failed: bool = True) -> argparse.Namespace:
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=True,
        self_test=None,
        retry_failed=retry_failed,
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

    def __init__(self, profile, **kwargs):
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


def _seed_row(sid: str, status: DispatchStatus, error_kind: str = "") -> DispatchLogRow:
    return DispatchLogRow(
        student_id=sid,
        name_kr="홍길동",
        email="ok@example.com" if status != DispatchStatus.SKIPPED else "",
        pdf_filename=f"{sid}_홍길동.pdf",
        pdf_sha256="a" * 64 if status != DispatchStatus.SKIPPED else "",
        attempt_at_kst=datetime(2026, 4, 30, 12, 0, 0, tzinfo=KST),
        mode=DispatchMode.PRODUCTION,
        status=status,
        smtp_message_id="<x@example.ac.kr>" if status == DispatchStatus.SUCCESS else "",
        error_kind=error_kind,
        error_detail="",
        exam_name="중간고사",
        cohort=CohortLabel.ALL,
    )


def test_retry_failed_only_failed_and_temporary(email_fixture, monkeypatch) -> None:
    """--retry-failed: only failed + temporary_failure students re-tried."""
    sids = [s[0] for s in email_fixture["students"]]
    # Seed: success/success/failed/temporary_failure/skipped
    log_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    append_dispatch_log_rows(
        log_path,
        [
            _seed_row(sids[0], DispatchStatus.SUCCESS),
            _seed_row(sids[1], DispatchStatus.SUCCESS),
            _seed_row(sids[2], DispatchStatus.FAILED, error_kind="gmail_api_unknown"),
            _seed_row(
                sids[3],
                DispatchStatus.TEMPORARY_FAILURE,
                error_kind="gmail_api_rate_limit",
            ),
            _seed_row(sids[4], DispatchStatus.SKIPPED, error_kind="invalid_email"),
        ],
    )

    _CountingDispatcher.captured = []
    monkeypatch.setattr("immersio.email.sender.GmailAPIDispatcher", _CountingDispatcher)
    rc = run_email_dispatch(_args(retry_failed=True))
    assert rc == 0

    # Only sids[2] (failed) + sids[3] (temporary_failure) re-tried
    assert set(_CountingDispatcher.captured) == {sids[2], sids[3]}
