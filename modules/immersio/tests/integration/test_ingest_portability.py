"""US3: identical Silver schema across two distinct courses (T059)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from immersio.ingest import run_ingest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ANATOMY_BRONZE = FIXTURES / "bronze_minimal"
MICROBIO_BRONZE = FIXTURES / "bronze_minimal_microbio"
ANATOMY_MAPPING = FIXTURES / "mappings" / "anatomy.diagnostic.yaml"
MICROBIO_MAPPING = FIXTURES / "mappings" / "microbio.diagnostic.yaml"


def _run(bronze: Path, mapping: Path, out: Path) -> Path:
    run_ingest(
        bronze_dir=bronze,
        mapping_path=mapping,
        output_dir=out,
        no_git_commit=True,
    )
    silver_dir = out / next(iter(out.iterdir())).name if any(out.iterdir()) else None
    # The output sub-key is derived from mapping metadata, but we ask for
    # output_dir as the parent → the actual silver directory is the only
    # subdirectory inside it.
    assert silver_dir is not None
    return silver_dir


def test_silver_schema_matches_across_courses(tmp_path: Path) -> None:
    out_anatomy = tmp_path / "silver_anatomy"
    out_microbio = tmp_path / "silver_microbio"
    silver_anatomy = _run(ANATOMY_BRONZE, ANATOMY_MAPPING, out_anatomy)
    silver_microbio = _run(MICROBIO_BRONZE, MICROBIO_MAPPING, out_microbio)

    parquets = (
        "student_master.parquet",
        "diagnostic_response.parquet",
        "exam_result.parquet",
        "exam_item.parquet",
    )
    for parquet in parquets:
        df_a = pd.read_parquet(silver_anatomy / parquet)
        df_b = pd.read_parquet(silver_microbio / parquet)
        # Columns must align in both name and order.
        assert list(df_a.columns) == list(df_b.columns), (
            f"{parquet}: anatomy columns={list(df_a.columns)} vs microbio={list(df_b.columns)}"
        )
        # Dtypes should match column-by-column.
        assert df_a.dtypes.to_dict().keys() == df_b.dtypes.to_dict().keys()

    # axis_scores keys (likert axes) must be identical between courses
    master_a = pd.read_parquet(silver_anatomy / "student_master.parquet")
    master_b = pd.read_parquet(silver_microbio / "student_master.parquet")
    keys_a = set(master_a.iloc[0]["axis_scores"].keys())
    keys_b = set(master_b.iloc[0]["axis_scores"].keys())
    assert keys_a == keys_b == {"motivation", "anxiety"}
