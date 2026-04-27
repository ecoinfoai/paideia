"""Phase A: single-item axis label & score still computed (T044)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import yaml

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")


def _single_item_mapping() -> dict:
    """Fixture mapping where motivation has only 1 likert item (single_item label)."""
    return {
        "metadata": {
            "semester": "2026-1",
            "course_slug": "anatomy",
            "course_name_kr": "인체구조와기능",
            "mapping_version": 1,
        },
        "axes": {"required": ["motivation"], "optional": []},
        "columns": [
            {"source": "학번", "kind": "identity"},
            {
                "source": "Q01_motivation_1",
                "kind": "likert",
                "axis": "motivation",
                "aggregate": "mean",
            },
        ],
    }


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
    (mapping_dir / "anatomy.diagnostic.yaml").write_text(
        yaml.safe_dump(_single_item_mapping()), encoding="utf-8"
    )
    return tmp_path


def test_single_item_axis_label_and_score(tmp_path: Path) -> None:
    """motivation has 1 likert item → label='single_item', alpha=None,
    score still computed for every responder.
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
    run_needs_map(args)

    sr = pd.read_parquet(
        tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy" / "scale_reliability.parquet"
    )
    motivation = sr[sr["axis_key"] == "motivation"].iloc[0]
    assert motivation["label"] == "single_item"
    assert pd.isna(motivation["cronbach_alpha"])

    fs = pd.read_parquet(
        tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy" / "factor_scores.parquet"
    )
    # 9 responders all have substantive single-item motivation score
    motivation_scores = fs["motivation"].dropna()
    assert len(motivation_scores) == 9
