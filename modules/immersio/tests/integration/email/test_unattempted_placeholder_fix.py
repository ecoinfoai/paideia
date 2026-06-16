"""Regression test — un-attempted SUCCESS placeholder rewrite (post-release fix).

The per-bundle loop in ``run_email_dispatch`` pre-populates each sendable
draft's log row with ``status=SUCCESS`` (the optimistic placeholder) before
the actual send loop runs. Two paths used to leak this placeholder into the
csv/manifest as fake successes:

    1. Self-test mode (``--self-test N --send``): the loop only iterates
       ``drafts_with_pdfs[:N]`` — the remaining ``M - N`` drafts retained
       their SUCCESS placeholder. Manifest counts inflated by ``M - N``.
    2. Production-send early exit (auth-fail / dispatcher exception):
       drafts after the failure point retained the SUCCESS placeholder.

Both paths now rewrite un-attempted SUCCESS rows so the csv/manifest report
honest counts and idempotent re-runs target the un-sent rows.
"""

from __future__ import annotations

import argparse
import io as _io

from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import DispatchStatus


def _args(self_test: int | None = None) -> argparse.Namespace:
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
        created_at_utc=None,
    )
    args._stdin = _io.StringIO("yes\n")
    return args


def test_self_test_unattempted_rows_marked_skipped(email_fixture, monkeypatch) -> None:
    """Self-test N=2 of 5 → 2 test_dummy + 3 SKIPPED (NOT 3 fake success).

    Before the fix, the 3 drafts not in the [:N=2] slice retained
    ``status=SUCCESS`` from the per-bundle placeholder, so the csv reported
    3 fake live-sends. Now those 3 rows must be SKIPPED with
    ``error_kind="self_test_not_attempted"``.
    """

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

    rc = run_email_dispatch(_args(self_test=2))
    assert rc == 0

    csv_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    text = csv_path.read_text(encoding="utf-8")

    # 2 drafts actually sent → test_dummy
    assert text.count(",test_dummy,") == 2
    # 3 drafts NOT in [:N] slice → SKIPPED with self_test_not_attempted
    assert text.count(",self_test_not_attempted,") == 3
    # No fake successes — every line with ",success," would mean a real
    # student email was reported as sent. Self-test must produce zero.
    assert ",success," not in text


def test_production_early_exit_unattempted_rows_marked_temporary_failure(
    email_fixture, monkeypatch
) -> None:
    """Production-send with auth-fail at draft #3 → un-attempted rows
    rewritten to TEMPORARY_FAILURE (NOT fake SUCCESS).

    Before the fix, drafts #4..#5 kept their SUCCESS placeholder when the
    loop returned early on auth-fail. Now they must be TEMPORARY_FAILURE
    with ``error_kind="not_attempted_after_early_exit"`` so an idempotent
    re-run under ``RetryMode.DEFAULT`` (skip success only) retries them.
    """
    call_count = {"n": 0}

    class _FakeDispatcher:
        def __init__(self, profile, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def send_one(self, draft, *, pdf_bytes):
            from immersio.email.sender import SendResult

            call_count["n"] += 1
            if call_count["n"] == 3:
                return SendResult(
                    status=DispatchStatus.FAILED,
                    error_kind="gmail_api_auth_failed",
                    error_detail="oauth subject mismatch",
                    gmail_server_message_id="",
                )
            return SendResult(
                status=DispatchStatus.SUCCESS,
                error_kind="",
                error_detail="",
                gmail_server_message_id=f"id-{draft.student_id}",
            )

        def sleep_between_sends(self):
            pass

    monkeypatch.setattr("immersio.email.sender.GmailAPIDispatcher", _FakeDispatcher)

    # confirm gate: type "yes" via injected stdin
    import io as _io

    args = _args()
    args._stdin = _io.StringIO("yes\n")
    args._stdout = _io.StringIO()

    rc = run_email_dispatch(args)
    # exit 5 = gmail_api_auth_failed
    assert rc == 5

    csv_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    text = csv_path.read_text(encoding="utf-8")

    # 2 drafts sent successfully before auth-fail
    assert text.count(",success,") == 2
    # 1 draft hit auth-fail → FAILED row with gmail_api_auth_failed
    assert text.count(",gmail_api_auth_failed,") == 1
    # Remaining 2 drafts (the 5-student fixture × all cohort) → TEMPORARY_FAILURE
    assert text.count(",temporary_failure,") == 2
    assert text.count(",not_attempted_after_early_exit,") == 2
