"""US2: atomicity — failing run never writes partial outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from immersio.ingest import IngestValidationError, run_ingest


def test_no_partial_outputs(corrupt_bronze: Path, corrupt_mapping: Path, tmp_path: Path) -> None:
    out = tmp_path / "silver"
    # First, run successfully so a Silver dir exists.
    run_ingest(
        bronze_dir=corrupt_bronze,
        mapping_path=corrupt_mapping,
        output_dir=out,
        no_git_commit=True,
    )
    silver_dir = out / "2026-1-anatomy"
    assert silver_dir.exists()

    initial_manifest = json.loads((silver_dir / "manifest.json").read_text(encoding="utf-8"))
    initial_created_at = initial_manifest["created_at"]

    # Now mutate diagnostic CSV to trigger Fail-Fast.
    diag_csv = corrupt_bronze / "진단평가" / "diag_test.csv"
    text = diag_csv.read_text(encoding="utf-8")
    diag_csv.write_text(text.replace("매우 그렇다", "매우 좋아요", 1), encoding="utf-8")

    with pytest.raises(IngestValidationError):
        run_ingest(
            bronze_dir=corrupt_bronze,
            mapping_path=corrupt_mapping,
            output_dir=out,
            no_git_commit=True,
        )
    # Existing Silver outputs must be untouched.
    after = json.loads((silver_dir / "manifest.json").read_text(encoding="utf-8"))
    assert after["created_at"] == initial_created_at
