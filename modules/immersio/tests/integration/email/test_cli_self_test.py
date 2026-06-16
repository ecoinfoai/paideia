"""CLI --self-test argument validation tests (T057)."""

from __future__ import annotations

import argparse

from immersio.email.pipeline import run_email_dispatch


def _args(**overrides) -> argparse.Namespace:
    base = dict(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=False,
        self_test=None,
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
    base.update(overrides)
    return argparse.Namespace(**base)


def test_self_test_without_send_allowed_as_dry_run(email_fixture) -> None:
    """v0.1.1 hotfix (spec.md Edge Cases): ``--self-test`` without ``--send``
    is no longer rejected — dry-run wins, self-test semantics applies to the
    preview composer (operator-To). Detailed assertions on csv/preview/manifest
    live in ``test_dry_run_self_test_combined.py`` (T035); this test merely
    guards the rejection lift: rc should be 0 (dry-run path), not 2 (old
    v0.1.0 rejection)."""
    rc = run_email_dispatch(_args(self_test=5, send=False))
    assert rc == 0, (
        f"dry-run + self-test should exit 0 (v0.1.1 spec.md Edge Cases — dry-run wins); got rc={rc}"
    )


def test_dry_run_default_no_self_test(email_fixture) -> None:
    """No --send + no --self-test → dry-run runs normally (exit 0)."""
    rc = run_email_dispatch(_args())
    assert rc == 0
