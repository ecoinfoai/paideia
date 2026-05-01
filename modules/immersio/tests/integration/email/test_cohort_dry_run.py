"""Integration test — cohort dry-run produces .eml + cohort 명단 (T100g2, US6 AS5)."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest
import responses

from .conftest import write_student_metrics_parquet
from immersio.email.pipeline import run_email_dispatch


def _args(*, cohort: str) -> argparse.Namespace:
    return argparse.Namespace(
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
        cohort=cohort,
        confirm_sample=None,
        bronze_csv=None,
        gold_pdf_dir=None,
        silver_master=None,
        silver_student_metrics=None,
        quiet=False,
        verbose=False,
    )


@responses.activate
def test_cohort_low_score_dry_run_emits_artefacts(email_fixture) -> None:
    """US6 AS5: dry-run + --cohort low_score → .eml(low only) + 3 cohort md + 0 Gmail call."""
    sids = [s[0] for s in email_fixture["students"]]
    silver_dir = (
        email_fixture["base"] / "data" / "silver" / "immersio" / "2026-1-anatomy"
    )
    # 2 low_score (45, 55) + 3 rest (75, 85, 90)
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

    rc = run_email_dispatch(_args(cohort="low_score"))
    assert rc == 0

    # (1) .eml previews only for low_score students (2)
    preview_dir = email_fixture["preview_dir"]
    eml_files = sorted(preview_dir.glob("*.eml"))
    assert len(eml_files) == 2
    eml_sids = {f.name.split("_")[0] for f in eml_files}
    assert eml_sids == {sids[0], sids[1]}

    # (2) 3 cohort md files all generated (regardless of cohort filter)
    gold = email_fixture["gold_email_dir"]
    assert (gold / "cohort_명단.md").is_file()
    assert (gold / "cohort_저득점_명단.md").is_file()
    assert (gold / "cohort_나머지_명단.md").is_file()

    # (3) No Gmail API HTTP calls
    assert len(responses.calls) == 0

    # (4) Dispatch log: 2 dry_run rows with cohort=low_score
    log_text = (gold / "메일_발송로그.csv").read_text(encoding="utf-8")
    dry_run_low_score = [
        line
        for line in log_text.splitlines()
        if "dry_run" in line and "low_score" in line
    ]
    assert len(dry_run_low_score) == 2


def test_cohort_silver_parquets_written(email_fixture) -> None:
    """Cohort silver parquets land in silver_email_dir."""
    sids = [s[0] for s in email_fixture["students"]]
    silver_dir = (
        email_fixture["base"] / "data" / "silver" / "immersio" / "2026-1-anatomy"
    )
    write_student_metrics_parquet(
        silver_dir,
        [
            (sids[0], "홍길동", 45.0),
            (sids[1], "김갑동", 80.0),
            (sids[2], "이순신", 30.0),
            (sids[3], "유관순", 90.0),
            (sids[4], "안중근", 55.0),
        ],
    )

    rc = run_email_dispatch(_args(cohort="all"))
    assert rc == 0

    assert (silver_dir / "cohort_저득점.parquet").is_file()
    assert (silver_dir / "cohort_나머지.parquet").is_file()
