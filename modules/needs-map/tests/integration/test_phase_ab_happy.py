"""Integration test: Phase A+B happy path with anatomy_full mapping (T040)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")
_FULL_MAPPING = Path("modules/needs-map/tests/fixtures/mappings/anatomy_full.diagnostic.yaml")


@pytest.fixture
def staged_input(tmp_path: Path) -> Path:
    """Copy synthetic Silver into tmp + drop the mapping at the default
    bronze/매핑/ location the pipeline looks for.
    """
    target = tmp_path
    silver_dir = target / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)
    for name in ("student_master.parquet", "diagnostic_response.parquet"):
        shutil.copy(
            _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy" / name,
            silver_dir / name,
        )
    mapping_dir = target / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True)
    shutil.copy(_FULL_MAPPING, mapping_dir / "anatomy.diagnostic.yaml")
    return target


def test_phase_ab_happy_path(staged_input: Path, tmp_path: Path) -> None:
    """Run Phase A+B with the full mapping, verify outputs + manifest."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B"}),
        input_root=staged_input,
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    manifest = run_needs_map(args)

    silver = tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy"
    assert (silver / "scale_reliability.parquet").is_file()
    assert (silver / "factor_scores.parquet").is_file()
    assert (silver / "manifest.json").is_file()

    sr = pd.read_parquet(silver / "scale_reliability.parquet")
    fs = pd.read_parquet(silver / "factor_scores.parquet")

    assert len(sr) == 8  # all 8 standard axes appear (full mapping, V6 strict)
    # 9 responders → 9 rows in factor_scores
    assert len(fs) == 9

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
    assert manifest.phases_executed == ["A", "B"]

    rows_per_phase = {entry.phase: entry.rows_written for entry in manifest.rows_per_phase}
    assert rows_per_phase["A"] == 8
    assert rows_per_phase["B"] == 9

    # manifest matches what was written
    on_disk = json.loads((silver / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["output_key"] == "2026-1-anatomy"
    assert on_disk["pii_redaction_validated"] is True


def test_phase_ab_motivation_z_normalized(staged_input: Path, tmp_path: Path) -> None:
    """motivation_z should have mean ≈ 0 and std ≈ 1 (population) over substantive rows."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B"}),
        input_root=staged_input,
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
    z_substantive = fs["motivation_z"].dropna()
    assert abs(z_substantive.mean()) < 1e-9
    assert abs(z_substantive.std(ddof=0) - 1.0) < 1e-9
