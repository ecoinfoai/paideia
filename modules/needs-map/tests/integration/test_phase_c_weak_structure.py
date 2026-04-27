"""Phase C weak structure: silhouette < 0.2 raises warning, run still succeeds (T062)."""

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


def test_weak_structure_warning_does_not_block(tmp_path: Path) -> None:
    """The 9-responder fixture has noisy clusters; weak_structure_warning may flip
    True (silhouette < 0.2) without aborting — Phase C still writes outputs.
    """
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
    # Outputs always written regardless of warning state
    silver = tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy"
    assert (silver / "cluster_assignment.parquet").is_file()
    # If silhouette_used < 0.2, the warning must flip True (FR-012)
    if manifest.cluster_silhouette_used is not None and manifest.cluster_silhouette_used < 0.2:
        assert manifest.weak_structure_warning is True
