"""Phase C k_override: --k forces a specific k regardless of silhouette argmax (T061)."""

from __future__ import annotations

import shutil
from pathlib import Path

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


def test_k_override_forces_k(tmp_path: Path) -> None:
    """--k 4 must force k_used=4 regardless of silhouette argmax."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        k_override=4,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    manifest = run_needs_map(args)
    # k_override may degrade to k=1 only when sample/k < 10 across the board;
    # 9 responders / k=4 = 2.25 → still expect cluster_k_used=4 (sample threshold
    # is candidate-level, not override-level).
    assert manifest.cluster_k_used == 4
