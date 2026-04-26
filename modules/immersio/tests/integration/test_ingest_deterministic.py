"""Determinism guarantees: byte-equal Parquet artefacts on identical inputs."""

from __future__ import annotations

import filecmp
import json
import shutil
from pathlib import Path

from immersio.ingest import run_ingest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BRONZE = FIXTURES / "bronze_minimal"
MAPPING = FIXTURES / "mappings" / "anatomy.diagnostic.yaml"

PARQUETS = (
    "student_master.parquet",
    "diagnostic_response.parquet",
    "exam_result.parquet",
    "exam_item.parquet",
)


def _run(out: Path) -> Path:
    run_ingest(
        bronze_dir=BRONZE,
        mapping_path=MAPPING,
        output_dir=out,
        no_git_commit=True,
    )
    return out / "2026-1-anatomy"


def test_two_runs_byte_equal(tmp_path: Path) -> None:
    silver_a = _run(tmp_path / "a")
    silver_b = _run(tmp_path / "b")

    for parquet in PARQUETS:
        assert filecmp.cmp(silver_a / parquet, silver_b / parquet, shallow=False), (
            f"Parquet output differs between deterministic runs: {parquet}"
        )

    manifest_a = json.loads((silver_a / "manifest.json").read_text())
    manifest_b = json.loads((silver_b / "manifest.json").read_text())
    # created_at differs deliberately; everything else must match.
    manifest_a.pop("created_at")
    manifest_b.pop("created_at")
    assert manifest_a == manifest_b


def test_input_hash_changes_when_input_changes(tmp_path: Path) -> None:
    """Mutating one Bronze input must update its sha256 in the manifest."""
    bronze_copy = tmp_path / "bronze"
    shutil.copytree(BRONZE, bronze_copy)

    silver_first = _run(tmp_path / "silver1")
    manifest_first = json.loads((silver_first / "manifest.json").read_text())
    diag_input_first = next(i for i in manifest_first["inputs"] if i["role"] == "diagnostic_csv")

    diag_csv = bronze_copy / "진단평가" / "diag_test.csv"
    text = diag_csv.read_text(encoding="utf-8")
    # Cosmetic mutation (BOM strip → re-add) shifts file bytes without breaking parse.
    diag_csv.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))

    run_ingest(
        bronze_dir=bronze_copy,
        mapping_path=MAPPING,
        output_dir=tmp_path / "silver2",
        no_git_commit=True,
    )
    manifest_second = json.loads(
        (tmp_path / "silver2" / "2026-1-anatomy" / "manifest.json").read_text()
    )
    diag_input_second = next(
        i for i in manifest_second["inputs"] if i["role"] == "diagnostic_csv"
    )
    assert diag_input_first["sha256"] != diag_input_second["sha256"]
