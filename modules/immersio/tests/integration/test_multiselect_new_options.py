"""Multiselect axes whose options are not predeclared in the mapping must
emit those options as DiagnosticResponse rows AND record them in the
manifest's multiselect_new_options dict, so operators can reconcile the
mapping post-hoc (spec Edge Case 'multiselect 신규 값')."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from immersio.ingest import run_ingest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BRONZE = FIXTURES / "bronze_minimal"
MAPPING = FIXTURES / "mappings" / "anatomy.diagnostic.yaml"


def test_multiselect_new_options_recorded(tmp_path: Path) -> None:
    out = tmp_path / "silver"
    run_ingest(
        bronze_dir=BRONZE,
        mapping_path=MAPPING,
        output_dir=out,
        no_git_commit=True,
    )
    silver_dir = out / "2026-1-anatomy"

    manifest = json.loads((silver_dir / "manifest.json").read_text(encoding="utf-8"))
    new_options = manifest["multiselect_new_options"]
    assert "interest_chapters" in new_options
    discovered = set(new_options["interest_chapters"])
    # The fixture diag CSV exposes 신경계, 근육계, 소화계, 순환계.
    assert {"신경계", "근육계", "소화계", "순환계"}.issubset(discovered)

    # DiagnosticResponse rows: each (student × option) one-hot exists.
    diag = pd.read_parquet(silver_dir / "diagnostic_response.parquet")
    multiselect_rows = diag[diag["axis_kind"] == "multiselect_onehot"]
    assert not multiselect_rows.empty
    assert {"신경계", "근육계"}.issubset(set(multiselect_rows["option_key"].dropna()))
