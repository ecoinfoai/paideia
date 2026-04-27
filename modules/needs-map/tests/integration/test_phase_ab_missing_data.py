"""Phase B missing-data branches: drop preserves NaN, mean_impute fills (T043)."""

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


def test_drop_policy_marks_missing_for_anxiety_all_missing_student(tmp_path: Path) -> None:
    """Student 2026194003 has no anxiety likert items → anxiety=None, anxiety_missing=True."""
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
    fs = pd.read_parquet(
        tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy" / "factor_scores.parquet"
    )
    student = fs[fs["student_id"] == "2026194003"].iloc[0]
    assert pd.isna(student["anxiety"])
    assert pd.isna(student["anxiety_z"])
    assert bool(student["anxiety_missing"]) is True


def test_drop_policy_marks_missing_for_motivation_partial_missing_student(tmp_path: Path) -> None:
    """Student 2026194002 has motivation_3 missing — under default drop policy
    the axis aggregate becomes NaN and missing flag flips True.
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
    fs = pd.read_parquet(
        tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy" / "factor_scores.parquet"
    )
    student = fs[fs["student_id"] == "2026194002"].iloc[0]
    assert pd.isna(student["motivation"])
    assert bool(student["motivation_missing"]) is True


def test_other_responders_have_no_motivation_missing(tmp_path: Path) -> None:
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
    fs = pd.read_parquet(
        tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy" / "factor_scores.parquet"
    )
    others = fs[~fs["student_id"].isin(["2026194002"])]
    assert not others["motivation_missing"].any()
