"""Integration test: Phase A+B+C happy path with anatomy_full mapping (T059)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")
_FULL_MAPPING = Path("modules/needs-map/tests/fixtures/mappings/anatomy_full.diagnostic.yaml")


def _stage(tmp_path: Path) -> Path:
    silver_dir = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)
    for name in ("student_master.parquet", "diagnostic_response.parquet"):
        shutil.copy(
            _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy" / name,
            silver_dir / name,
        )
    mapping_dir = tmp_path / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True)
    shutil.copy(_FULL_MAPPING, mapping_dir / "anatomy.diagnostic.yaml")
    return tmp_path


def test_phase_abc_writes_cluster_assignment(tmp_path: Path) -> None:
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    manifest = run_needs_map(args)

    silver = tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy"
    assert (silver / "cluster_assignment.parquet").is_file()

    ca = pd.read_parquet(silver / "cluster_assignment.parquet")
    assert "cluster_id" in ca.columns
    assert "student_id" in ca.columns
    assert (ca["cluster_id"] >= 0).all()

    assert manifest.cluster_k_used is not None
    assert 1 <= manifest.cluster_k_used <= 6
    if manifest.cluster_k_used > 1:
        assert manifest.cluster_silhouette_used is not None
    assert manifest.phases_executed == ["A", "B", "C"]
