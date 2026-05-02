"""CLI --self-test argument validation tests (T057)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

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


def test_self_test_without_send_rejected(email_fixture) -> None:
    """--self-test 5 without --send → exit 2."""
    rc = run_email_dispatch(_args(self_test=5, send=False))
    assert rc == 2


def test_dry_run_default_no_self_test(email_fixture) -> None:
    """No --send + no --self-test → dry-run runs normally (exit 0)."""
    rc = run_email_dispatch(_args())
    assert rc == 0
