"""Archival replay test (T093, ADR-022 + Constitution V).

First send → outputs land in gold dir. Second send (different sent
date) → first run's outputs move to ``_archive/{ISO}__v{ver}/`` and
second run's outputs occupy the gold dir. Phase 6 PDF input dir
(``이메일_발송용/``) is preserved across both runs (whitelist).
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import DispatchStatus


def _args(*, sent_date: str) -> argparse.Namespace:
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date=sent_date,
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


class _AlwaysSucceeds:
    def __init__(self, profile, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def send_one(self, draft, *, pdf_bytes):
        from immersio.email.sender import SendResult

        return SendResult(
            status=DispatchStatus.SUCCESS,
            error_kind="",
            error_detail="",
            gmail_server_message_id=f"id-{draft.student_id}",
        )


def test_second_run_archives_first(email_fixture, monkeypatch) -> None:
    """Re-running with a different sent-date moves prior outputs into _archive/."""
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _AlwaysSucceeds
    )

    # Run 1: sent-date 2026-05-01
    rc1 = run_email_dispatch(_args(sent_date="2026-05-01"))
    assert rc1 == 0
    gold_dir = email_fixture["gold_email_dir"]
    assert (gold_dir / "메일_발송로그.csv").is_file()
    assert (gold_dir / "manifest_email.json").is_file()
    log_v1 = (gold_dir / "메일_발송로그.csv").read_bytes()

    # Run 2: sent-date 2026-05-08 (week later, different artefacts)
    rc2 = run_email_dispatch(_args(sent_date="2026-05-08"))
    assert rc2 == 0

    # _archive/ exists with at least one timestamped subdir
    archive_root = gold_dir / "_archive"
    assert archive_root.is_dir()
    archive_subdirs = [p for p in archive_root.iterdir() if p.is_dir()]
    assert len(archive_subdirs) >= 1

    # First run's log is preserved inside one of the archive subdirs
    archived_logs = list(archive_root.rglob("메일_발송로그.csv"))
    assert len(archived_logs) >= 1
    # The archived log content matches run 1
    assert any(p.read_bytes() == log_v1 for p in archived_logs)

    # Phase 6 PDF input dir is preserved at the canonical path
    pdf_dir = email_fixture["gold_pdf_dir"]
    assert pdf_dir.is_dir()
    assert sorted(pdf_dir.glob("*.pdf"))  # PDFs not archived away


def test_archival_no_op_on_first_run(email_fixture, monkeypatch) -> None:
    """First run with no prior outputs → no _archive/ subdir created."""
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _AlwaysSucceeds
    )
    rc = run_email_dispatch(_args(sent_date="2026-05-01"))
    assert rc == 0
    archive_root = email_fixture["gold_email_dir"] / "_archive"
    # Either absent OR empty (no archive subdir)
    if archive_root.exists():
        assert list(archive_root.iterdir()) == []
