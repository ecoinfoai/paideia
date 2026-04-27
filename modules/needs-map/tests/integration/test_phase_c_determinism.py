"""Phase C determinism: two runs with same seed → byte-equal cluster_assignment (T060)."""

from __future__ import annotations

import filecmp
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


def test_phase_c_two_runs_byte_equal(tmp_path: Path) -> None:
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args_a = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C"}),
        input_root=_stage(tmp_path / "in_a"),
        output_root=tmp_path / "out_a",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        created_at_utc="2026-04-27T00:00:00Z",
    )
    args_b = args_a.model_copy(
        update={"input_root": _stage(tmp_path / "in_b"), "output_root": tmp_path / "out_b"}
    )

    run_needs_map(args_a)
    run_needs_map(args_b)

    silver_a = tmp_path / "out_a" / "silver" / "needs-map" / "2026-1-anatomy"
    silver_b = tmp_path / "out_b" / "silver" / "needs-map" / "2026-1-anatomy"

    assert filecmp.cmp(
        silver_a / "cluster_assignment.parquet",
        silver_b / "cluster_assignment.parquet",
        shallow=False,
    )

    # cluster_id must be identical per student_id (not just byte-equal, but
    # semantically identical assignment under the same seed).
    a = pd.read_parquet(silver_a / "cluster_assignment.parquet").set_index("student_id")
    b = pd.read_parquet(silver_b / "cluster_assignment.parquet").set_index("student_id")
    assert (a["cluster_id"] == b["cluster_id"]).all()
