"""--sent-date default + format tests (T103, FR-B05)."""

from __future__ import annotations

import argparse
import io
from datetime import date, datetime, timedelta, timezone

import pytest
from immersio.email.pipeline import _parse_sent_date, run_email_dispatch

KST = timezone(timedelta(hours=9))


def test_parse_sent_date_explicit() -> None:
    """--sent-date 2026-05-01 → date(2026, 5, 1)."""
    assert _parse_sent_date("2026-05-01") == date(2026, 5, 1)


def test_parse_sent_date_default_today_kst() -> None:
    """No --sent-date → today() in KST."""
    parsed = _parse_sent_date(None)
    today_kst = datetime.now(tz=KST).date()
    assert parsed == today_kst


def test_parse_sent_date_invalid_format_rejected() -> None:
    """Wrong separator (2026/05/01) → ValueError."""
    with pytest.raises(ValueError):
        _parse_sent_date("2026/05/01")


def test_parse_sent_date_invalid_calendar_rejected() -> None:
    """Out-of-range calendar (2026-13-01) → ValueError."""
    with pytest.raises(ValueError):
        _parse_sent_date("2026-13-01")


def test_cli_invalid_sent_date_returns_1(email_fixture) -> None:
    """CLI --sent-date 2026/05/01 → exit 1 + stderr."""
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026/05/01",
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
    args._stdin = io.StringIO("")
    args._stdout = io.StringIO()
    rc = run_email_dispatch(args)
    assert rc == 1
