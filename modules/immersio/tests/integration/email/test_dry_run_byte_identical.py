"""Integration test — same input + same --sent-date → byte-identical .eml + parquet (T039)."""

from __future__ import annotations

import argparse

import responses

from immersio.email.pipeline import run_email_dispatch


def _args() -> argparse.Namespace:
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
def test_two_dry_runs_produce_byte_identical_eml(email_fixture) -> None:
    """SC-010: same input + same --sent-date → identical .eml hashes."""
    # First run
    assert run_email_dispatch(_args()) == 0
    preview_dir = email_fixture["preview_dir"]
    first = {
        p.name: p.read_bytes() for p in sorted(preview_dir.glob("*.eml"))
    }

    # Wipe and re-run
    for p in preview_dir.glob("*.eml"):
        p.unlink()

    assert run_email_dispatch(_args()) == 0
    second = {
        p.name: p.read_bytes() for p in sorted(preview_dir.glob("*.eml"))
    }

    assert set(first.keys()) == set(second.keys())
    for name in first:
        assert first[name] == second[name], f"non-deterministic .eml: {name}"


@responses.activate
def test_silver_mapping_parquet_byte_identical_two_runs(email_fixture) -> None:
    silver_path = (
        email_fixture["base"] / "data" / "silver" / "immersio"
        / "2026-1-anatomy" / "학번_이메일_매핑.parquet"
    )

    assert run_email_dispatch(_args()) == 0
    first = silver_path.read_bytes()

    silver_path.unlink()
    assert run_email_dispatch(_args()) == 0
    second = silver_path.read_bytes()

    assert first == second
