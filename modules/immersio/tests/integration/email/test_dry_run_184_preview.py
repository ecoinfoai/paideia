"""Integration test — dry-run preview produces .eml files with 0 Gmail call (T038).

Covers SC-001 (correct mapping) + SC-003 (no external mail server call).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import responses

from immersio.email.pipeline import run_email_dispatch


def _args(profile: str = "alpha-prof") -> argparse.Namespace:
    return argparse.Namespace(
        profile=profile,
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


@responses.activate
def test_dry_run_creates_5_preview_eml_files(email_fixture) -> None:
    """5 student fixture → 5 .eml files + 0 HTTPS calls."""
    rc = run_email_dispatch(_args())
    assert rc == 0

    preview_dir = email_fixture["preview_dir"]
    eml_files = sorted(preview_dir.glob("*.eml"))
    assert len(eml_files) == 5

    # SC-003: no Gmail API HTTP call (mock library reports 0 calls)
    assert len(responses.calls) == 0


@responses.activate
def test_dry_run_eml_each_student_matches_correct_pdf(email_fixture) -> None:
    """SC-001: each .eml's To/Subject/attachment all reference the same student."""
    rc = run_email_dispatch(_args())
    assert rc == 0

    preview_dir = email_fixture["preview_dir"]
    for sid, name, email in email_fixture["students"]:
        eml = preview_dir / f"{sid}_{name}.eml"
        assert eml.is_file()
        text = eml.read_text(encoding="utf-8", errors="replace")
        assert sid in text
        assert email in text


@responses.activate
def test_dry_run_writes_manifest_log_report(email_fixture) -> None:
    rc = run_email_dispatch(_args())
    assert rc == 0
    gold_dir = email_fixture["gold_email_dir"]
    assert (gold_dir / "manifest_email.json").is_file()
    assert (gold_dir / "메일_발송로그.csv").is_file()
    assert (gold_dir / "메일_발송보고서.md").is_file()
