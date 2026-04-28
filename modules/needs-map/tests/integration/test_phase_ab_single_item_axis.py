"""Phase A: single-item axis label & score still computed (T044)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import yaml

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")


_REQUIRED_AXES_8 = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def _single_item_mapping() -> dict:
    """v0.1.1 v2 mapping (V6 strict 8-axis required) where motivation carries
    only 1 likert item — every other axis has a single likert column too,
    so the test scopes its assertion to the motivation single_item branch.
    """
    columns: list[dict] = [{"source": "학번", "kind": "identity"}]
    # Source columns chosen to match silver_minimal so substantive scores
    # land for every responder.
    source_for: dict[str, str] = {
        "digital_efficacy": "Q_digital_efficacy",
        "motivation": "Q01_motivation_1",
        "time_availability": "Q_time_availability",
        "material_preference": "Q_material_preference",
        "study_strategy": "Q05_study_strategy_1",
        "study_environment": "Q07_study_environment_1",
        "social_learning": "Q_social_learning",
        "feedback_seeking": "Q_feedback_seeking",
    }
    for axis in _REQUIRED_AXES_8:
        columns.append(
            {
                "source": source_for[axis],
                "kind": "likert",
                "axis": axis,
                "aggregate": "mean",
            }
        )
    return {
        "metadata": {
            "semester": "2026-1",
            "course_slug": "anatomy",
            "course_name_kr": "인체구조와기능",
            "mapping_version": 2,
        },
        "axes": {"required": list(_REQUIRED_AXES_8), "optional": []},
        "columns": columns,
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
