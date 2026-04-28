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
    """v0.1.1 V6 strict: axes.required = all 8 axes always, but 3 of them
    can have ZERO likert items (single_select-only). Those axes are reported
    as scoring-skipped (no_items label + factor None) without dropping them
    from manifest.standard_axes_used (V6 strict supersedes the v0.1.0 drop
    pattern).
    """
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

    # V6 strict — axes.required is always the full 8, so standard_axes_used
    # carries all 8 and standard_axes_skipped is empty.
    assert sorted(manifest.standard_axes_used) == sorted(
        [
            "digital_efficacy",
            "motivation",
            "time_availability",
            "material_preference",
            "study_strategy",
            "study_environment",
            "social_learning",
            "feedback_seeking",
        ]
    )
    assert manifest.standard_axes_skipped == []

    sr = pd.read_parquet(
        tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy" / "scale_reliability.parquet"
    )
    fs = pd.read_parquet(
        tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy" / "factor_scores.parquet"
    )
    # The 3 axes mapped via single_select-only carry n_items=0 + label='no_items'
    # and their factor score columns are None for every responder.
    for axis in ("digital_efficacy", "social_learning", "feedback_seeking"):
        sr_row = sr[sr["axis_key"] == axis].iloc[0]
        assert sr_row["n_items"] == 0
        assert sr_row["label"] == "no_items"
        assert fs[axis].isna().all()
        assert fs[f"{axis}_z"].isna().all()
        assert fs[f"{axis}_missing"].all()
