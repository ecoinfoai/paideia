"""Integration test — two-batch cohort send (T100f, SC-015 + SC-016)."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from .conftest import write_student_metrics_parquet
from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import DispatchStatus


def _args(*, cohort: str) -> argparse.Namespace:
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
        cohort=cohort,
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


def test_two_batch_low_then_rest(email_fixture, monkeypatch) -> None:
    """SC-015: 1차 low_score 발송 → 2차 rest 발송, 1차 학생 도달 0.

    5 fixture students: 2 low_score (45.0, 55.0) + 3 rest (75.0, 85.0, 90.0).
    """
    sids = [s[0] for s in email_fixture["students"]]
    silver_dir = (
        email_fixture["base"] / "data" / "silver" / "immersio" / "2026-1-anatomy"
    )
    write_student_metrics_parquet(
        silver_dir,
        [
            (sids[0], "홍길동", 45.0),
            (sids[1], "김갑동", 55.0),
            (sids[2], "이순신", 75.0),
            (sids[3], "유관순", 85.0),
            (sids[4], "안중근", 90.0),
        ],
    )

    # Batch 1 — low_score only
    _CountingDispatcher.captured = []
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _CountingDispatcher
    )
    rc1 = run_email_dispatch(_args(cohort="low_score"))
    assert rc1 == 0
    batch1 = list(_CountingDispatcher.captured)
    assert set(batch1) == {sids[0], sids[1]}

    # Batch 2 — rest only. SC-015: 1차 학생 도달 0.
    _CountingDispatcher.captured = []
    rc2 = run_email_dispatch(_args(cohort="rest"))
    assert rc2 == 0
    batch2 = list(_CountingDispatcher.captured)
    assert set(batch2) == {sids[2], sids[3], sids[4]}
    # 1차 학생들이 batch2 에 0 도달
    assert not (set(batch1) & set(batch2))


def test_sc016_low_score_count_matches_send_count(
    email_fixture, monkeypatch
) -> None:
    """SC-016: 학생지표 의 score_percent < 60 학생 수 == 1차 발송 (success+skipped) 합계."""
    sids = [s[0] for s in email_fixture["students"]]
    silver_dir = (
        email_fixture["base"] / "data" / "silver" / "immersio" / "2026-1-anatomy"
    )
    # 2 low_score in metrics
    write_student_metrics_parquet(
        silver_dir,
        [
            (sids[0], "홍길동", 45.0),
            (sids[1], "김갑동", 55.0),
            (sids[2], "이순신", 75.0),
            (sids[3], "유관순", 85.0),
            (sids[4], "안중근", 90.0),
        ],
    )

    _CountingDispatcher.captured = []
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _CountingDispatcher
    )
    rc = run_email_dispatch(_args(cohort="low_score"))
    assert rc == 0

    log_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    text = log_path.read_text(encoding="utf-8")
    # Count rows where cohort=low_score (success or skipped)
    low_score_rows = [
        line for line in text.splitlines()
        if "low_score" in line and ("success" in line or "skipped" in line)
    ]
    # 2 low_score students in metrics → 2 send rows
    assert len(low_score_rows) == 2
