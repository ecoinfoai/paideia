"""T004 — write_combined_silver must produce owner-only (0o600) parquet.

Security requirement: 진단×시험결합.parquet carries student PII
(student_id, name_kr) and must never be world-readable (DAR-01 / SC-006).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pyarrow.parquet as pq
import pytest
from immersio.combine.joiner import join_silver_phase3
from immersio.combine.silver_writer import write_combined_silver


def _load_builder() -> ModuleType:
    here = Path(__file__).resolve()
    builder_path = here.parents[2] / "fixtures" / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location("build_silver_phase3", builder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def combined_df(tmp_path_factory: pytest.TempPathFactory):
    """Minimal valid 60-column DataFrame from the Phase 3 fixture builder."""
    root = tmp_path_factory.mktemp("silver_perm_combine")
    builder = _load_builder()
    builder.build_silver_phase3_minimal(root)

    nm = root / "silver" / "needs-map" / "2026-1-anatomy"
    im = root / "silver" / "immersio" / "2026-1-anatomy"
    cluster_names_raw = json.loads((nm / "cluster_names.json").read_text(encoding="utf-8"))
    cluster_names = {int(k): v for k, v in cluster_names_raw.items()}

    df, _ = join_silver_phase3(
        student_master=pq.read_table(im / "student_master.parquet").to_pandas(),
        factor_scores=pq.read_table(nm / "factor_scores.parquet").to_pandas(),
        cluster_assignment=pq.read_table(nm / "cluster_assignment.parquet").to_pandas(),
        cluster_names=cluster_names,
        student_metrics=pq.read_table(im / "학생지표.parquet").to_pandas(),
        diagnostic_response=pq.read_table(im / "diagnostic_response.parquet").to_pandas(),
    )
    return df


def test_combined_silver_is_owner_only(combined_df, tmp_path: Path, assert_owner_only) -> None:
    """DAR-01: 진단×시험결합.parquet must be chmod 0o600 (no group/other bits)."""
    out = tmp_path / "진단×시험결합.parquet"
    write_combined_silver(combined_df, out)
    assert_owner_only(out)
