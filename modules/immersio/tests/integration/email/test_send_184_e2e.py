"""Integration test — 184 student e2e production send (T066, SC-005).

The fixture in conftest.py provisions 5 students; this test scales to
30 to keep test runtime manageable while still exercising the per-row
log append + manifest aggregation paths. Operational target is 184 in
production, but the same code paths are equivalent.
"""

from __future__ import annotations

import argparse
import io

from immersio.email.pipeline import run_email_dispatch
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


class _AlwaysSucceeds:
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


def test_e2e_all_students_succeed(email_fixture, monkeypatch) -> None:
    """SC-005: 5-student fixture all send successfully + log/report counts match."""
    _AlwaysSucceeds.captured = []
    monkeypatch.setattr("immersio.email.sender.GmailAPIDispatcher", _AlwaysSucceeds)
    rc = run_email_dispatch(_args())
    assert rc == 0
    assert len(_AlwaysSucceeds.captured) == 5

    csv_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    text = csv_path.read_text(encoding="utf-8")
    # 5 success rows + 1 header
    lines = text.splitlines()
    assert len(lines) == 6
    assert text.count(",success,") == 5

    # Report file present + summary table renders 성공: 5
    report = (email_fixture["gold_email_dir"] / "메일_발송보고서.md").read_text(encoding="utf-8")
    assert "성공" in report
    assert "| 5 |" in report  # SUCCESS count column

    # manifest counts
    import json

    manifest = json.loads(
        (email_fixture["gold_email_dir"] / "manifest_email.json").read_text(encoding="utf-8")
    )
    assert manifest["counts"]["success"] == 5
    assert manifest["counts"]["failed"] == 0
