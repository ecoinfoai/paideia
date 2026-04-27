"""Phase A+B with partial mapping: skipped axes recorded in manifest (T042)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")
_PARTIAL_MAPPING = Path(
    "modules/needs-map/tests/fixtures/mappings/anatomy_partial.diagnostic.yaml"
)


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
    shutil.copy(_PARTIAL_MAPPING, mapping_dir / "anatomy.diagnostic.yaml")
    return tmp_path


def test_partial_mapping_skips_three_axes(tmp_path: Path) -> None:
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    manifest = run_needs_map(args)

    assert sorted(manifest.standard_axes_used) == ["anxiety", "life_context", "motivation"]
    assert sorted(manifest.standard_axes_skipped) == [
        "interest",
        "prior_knowledge",
        "self_efficacy",
    ]

    fs = pd.read_parquet(
        tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy" / "factor_scores.parquet"
    )
    for axis in ("self_efficacy", "interest", "prior_knowledge"):
        assert fs[axis].isna().all()
        assert fs[f"{axis}_z"].isna().all()
        assert fs[f"{axis}_missing"].all()
