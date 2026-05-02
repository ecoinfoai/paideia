"""--created-at-utc external override (M3 advisory).

Re-runs with the same --created-at-utc must produce byte-identical
manifest_email.json (and downstream report.md timestamps stay pinned).
"""

from __future__ import annotations

import argparse
import io
import json

import pytest


def _args(*, created_at_utc: str | None = None) -> argparse.Namespace:
    args = argparse.Namespace(
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
        created_at_utc=created_at_utc,
        quiet=False,
        verbose=False,
    )
    args._stdin = io.StringIO("")
    args._stdout = io.StringIO()
    return args


def test_explicit_override_pins_manifest_timestamps(email_fixture) -> None:
    """Two dry-runs with same --created-at-utc → identical manifest timestamps."""
    from immersio.email.pipeline import run_email_dispatch

    rc1 = run_email_dispatch(_args(created_at_utc="2026-05-01T03:00:00Z"))
    assert rc1 == 0

    manifest_path = email_fixture["gold_email_dir"] / "manifest_email.json"
    payload1 = json.loads(manifest_path.read_text(encoding="utf-8"))

    rc2 = run_email_dispatch(_args(created_at_utc="2026-05-01T03:00:00Z"))
    assert rc2 == 0
    payload2 = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload1["started_at_kst"] == payload2["started_at_kst"]
    assert payload1["completed_at_kst"] == payload2["completed_at_kst"]


def test_invalid_format_rejected(email_fixture) -> None:
    """No trailing 'Z' → exit 1 + stderr."""
    from immersio.email.pipeline import run_email_dispatch

    rc = run_email_dispatch(_args(created_at_utc="2026-05-01T03:00:00"))
    assert rc == 1


def test_no_override_uses_current_time(email_fixture) -> None:
    """No --created-at-utc → wall clock (existing behaviour preserved)."""
    from immersio.email.pipeline import run_email_dispatch

    rc = run_email_dispatch(_args(created_at_utc=None))
    assert rc == 0
