"""TestProfile + dummy fixture integration test (T085, SC-013/014/TC-004)."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from .conftest import make_test_profile
from immersio.email.dummy_fixture import generate_dummy_pdfs
from immersio.email.pipeline import run_email_dispatch


def _args(*, profile: str = "alpha-dev") -> argparse.Namespace:
    args = argparse.Namespace(
        profile=profile,
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=False,  # dry-run for cleanliness
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
    return args


def test_test_profile_uses_dummy_fixture_dir(
    tmp_path: Path, monkeypatch
) -> None:
    """SC-013 + SC-014: TestProfile activates dummy_fixture_dir as PDF source."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    fixture_dir = tmp_path / "test_fixtures"
    make_test_profile(home, fixture_dir, profile_name="alpha-dev")

    # Generate 2 dummy PDFs into the fixture dir (matches dummy_students)
    generate_dummy_pdfs(
        fixture_dir,
        [("1234567990", "더미일"), ("1234567991", "더미이")],
    )

    rc = run_email_dispatch(_args())
    assert rc == 0

    # Preview routed to _test/ subtree (TC-004)
    preview_dir = (
        tmp_path / "tmp" / "immersio_email_preview" / "2026-1-anatomy" / "_test"
    )
    eml_files = sorted(preview_dir.glob("*.eml"))
    # 2 dummy students × 2 pool addresses → 1:1 → 2 .eml
    assert len(eml_files) == 2

    # Production output dir untouched (no production .eml)
    prod_preview = (
        tmp_path / "tmp" / "immersio_email_preview" / "2026-1-anatomy"
    )
    prod_eml_at_root = list(prod_preview.glob("*.eml"))
    assert prod_eml_at_root == []  # Only _test/ has .eml


def test_test_profile_rejects_explicit_bronze_path(
    tmp_path: Path, monkeypatch
) -> None:
    """TestProfile + --bronze-csv → exit 2 (operator paths meaningless)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    fixture_dir = tmp_path / "test_fixtures"
    make_test_profile(home, fixture_dir, profile_name="alpha-dev")
    generate_dummy_pdfs(
        fixture_dir,
        [("1234567990", "더미일"), ("1234567991", "더미이")],
    )

    args = _args()
    args.bronze_csv = Path("/some/explicit/path.csv")
    rc = run_email_dispatch(args)
    assert rc == 2
