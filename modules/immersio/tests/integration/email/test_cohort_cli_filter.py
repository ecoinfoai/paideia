"""Integration test — CLI --cohort flag (T100g)."""

from __future__ import annotations

import argparse
import io

import pytest

from .conftest import write_student_metrics_parquet
from immersio.cli.main import _build_parser
from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import DispatchStatus


def _args(*, cohort: str) -> argparse.Namespace:
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
        cohort=cohort,
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
    return args


def test_cohort_default_is_all() -> None:
    """argparse default for --cohort is 'all'."""
    parser = _build_parser()
    args = parser.parse_args(
        [
            "email",
            "--profile",
            "alpha-prof",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--exam-name",
            "중간고사",
        ]
    )
    assert args.cohort == "all"


def test_invalid_cohort_value_rejected() -> None:
    """argparse choices rejects unknown cohort label → exit 2."""
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "email",
                "--profile",
                "alpha-prof",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--exam-name",
                "중간고사",
                "--cohort",
                "foo",
            ]
        )
    assert exc_info.value.code == 2


def test_cohort_low_score_filters_to_low(email_fixture, monkeypatch) -> None:
    """--cohort low_score: only low-score students reach the preview."""
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

    rc = run_email_dispatch(_args(cohort="low_score"))
    assert rc == 0

    preview_dir = email_fixture["preview_dir"]
    eml_files = sorted(preview_dir.glob("*.eml"))
    # 3 low_score students (45.0, 30.0, 55.0)
    assert len(eml_files) == 3
    eml_sids = {f.name.split("_")[0] for f in eml_files}
    assert eml_sids == {sids[0], sids[2], sids[4]}
