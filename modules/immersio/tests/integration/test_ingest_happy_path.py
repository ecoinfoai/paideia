"""End-to-end happy-path test for run_ingest."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from immersio.ingest import run_ingest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BRONZE = FIXTURES / "bronze_minimal"
MAPPING = FIXTURES / "mappings" / "anatomy.diagnostic.yaml"


def test_run_ingest_happy_path(tmp_path: Path) -> None:
    output_parent = tmp_path / "silver"
    manifest = run_ingest(
        bronze_dir=BRONZE,
        mapping_path=MAPPING,
        output_dir=output_parent,
        no_git_commit=True,
    )

    silver_dir = output_parent / "2026-1-anatomy"
    assert (silver_dir / "student_master.parquet").is_file()
    assert (silver_dir / "diagnostic_response.parquet").is_file()
    assert (silver_dir / "exam_result.parquet").is_file()
    assert (silver_dir / "exam_item.parquet").is_file()
    assert (silver_dir / "manifest.json").is_file()

    masters = pd.read_parquet(silver_dir / "student_master.parquet")

    # Roster has 5 students, plus 1 off-roster diagnostic respondent (2026099001)
    # plus 1 off-roster OMR-only respondent (2026099002).
    on_roster = masters[masters["on_roster"]]
    off_roster = masters[~masters["on_roster"]]
    assert len(on_roster) == 5
    assert len(off_roster) == 2
    assert set(off_roster["student_id"]) == {"2026099001", "2026099002"}

    # exam_absent flag: roster student E (2026000005) is absent in fixture.
    absent_roster = on_roster[on_roster["exam_absent"]]
    assert set(absent_roster["student_id"]) == {"2026000005"}

    # axis_scores keys must include the likert axes (multiselect/freetext live
    # in DiagnosticResponse rows only — see data-model §1).
    axis_scores_record = masters.iloc[0]["axis_scores"]
    assert {"motivation", "anxiety"}.issubset(set(axis_scores_record.keys()))

    # Manifest sanity
    manifest_payload = json.loads((silver_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["output_key"] == "2026-1-anatomy"
    assert manifest_payload["row_counts"]["student_master"] == len(masters)
    # unrecognized_files (T025 C5): _unused_backup.txt at bronze_minimal root.
    assert any("_unused_backup.txt" in path for path in manifest_payload["unrecognized_files"])
    # multiselect_new_options is dict[str, list[str]] (T025 C2)
    assert isinstance(manifest_payload["multiselect_new_options"], dict)
    assert "interest_chapters" in manifest_payload["multiselect_new_options"]

    # mirror returned manifest
    assert manifest.row_counts.student_master == len(masters)
