"""SC-008 cross-course isolation (T117).

Two distinct OutputKey runs (2026-1-anatomy + 2026-1-microbiology) write into
the same output_root. Verify (a) two separate silver/gold tree subdirectories,
(b) each manifest's output_key matches its directory, (c) re-running anatomy
does NOT touch microbiology files (archival isolation).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")


def _stage_anatomy(tmp_path: Path) -> Path:
    silver_dir = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)
    for name in ("student_master.parquet", "diagnostic_response.parquet"):
        shutil.copy(
            _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy" / name,
            silver_dir / name,
        )
    mapping_dir = tmp_path / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True)
    shutil.copy(
        Path("modules/needs-map/tests/fixtures/mappings/anatomy_full.diagnostic.yaml"),
        mapping_dir / "anatomy.diagnostic.yaml",
    )
    return tmp_path


def _stage_microbiology(tmp_path: Path) -> None:
    """Reuse anatomy fixture with course_slug='microbiology' label.

    Same data shape; what we test is *output directory isolation*, not the
    domain meaning of the responses.
    """
    src_silver = _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy"
    dst_silver = tmp_path / "silver" / "immersio" / "2026-1-microbiology"
    dst_silver.mkdir(parents=True)

    # Rewrite course_slug column on both parquets
    import pandas as pd

    for name in ("student_master.parquet", "diagnostic_response.parquet"):
        df = pd.read_parquet(src_silver / name)
        if "course_slug" in df.columns:
            df["course_slug"] = "microbiology"
        pq.write_table(pa.Table.from_pandas(df), dst_silver / name)

    # v0.1.1 V6 strict mapping: required = full 8-axis vocabulary. Source
    # columns picked to match silver_minimal so substantive scores land for
    # every responder under both course slugs (the test only checks output
    # directory isolation, not score values).
    axes_8 = (
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    )
    source_for = {
        "digital_efficacy": "Q_digital_efficacy",
        "motivation": "Q01_motivation_1",
        "time_availability": "Q_time_availability",
        "material_preference": "Q_material_preference",
        "study_strategy": "Q05_study_strategy_1",
        "study_environment": "Q07_study_environment_1",
        "social_learning": "Q_social_learning",
        "feedback_seeking": "Q_feedback_seeking",
    }
    mapping = {
        "metadata": {
            "semester": "2026-1",
            "course_slug": "microbiology",
            "course_name_kr": "미생물학",
            "mapping_version": 2,
        },
        "axes": {"required": list(axes_8), "optional": []},
        "columns": [
            {"source": "학번", "kind": "identity"},
            *[
                {
                    "source": source_for[axis],
                    "kind": "likert",
                    "axis": axis,
                    "aggregate": "mean",
                }
                for axis in axes_8
            ],
        ],
    }
    mapping_dir = tmp_path / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True, exist_ok=True)
    (mapping_dir / "microbiology.diagnostic.yaml").write_text(
        yaml.safe_dump(mapping), encoding="utf-8"
    )


def test_two_courses_isolated_output_dirs(tmp_path: Path) -> None:
    """Anatomy + microbiology write to distinct OutputKey subdirectories."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    in_dir = _stage_anatomy(tmp_path / "in")
    _stage_microbiology(in_dir)
    out_dir = tmp_path / "out"

    args_anatomy = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B"}),
        input_root=in_dir,
        output_root=out_dir,
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    args_microbio = args_anatomy.model_copy(update={"course_slug": "microbiology"})

    m_a = run_needs_map(args_anatomy)
    m_m = run_needs_map(args_microbio)

    silver_a = out_dir / "silver" / "needs-map" / "2026-1-anatomy"
    silver_m = out_dir / "silver" / "needs-map" / "2026-1-microbiology"

    assert silver_a.is_dir()
    assert silver_m.is_dir()
    assert m_a.output_key == "2026-1-anatomy"
    assert m_m.output_key == "2026-1-microbiology"
    # File names overlap (factor_scores.parquet etc.) but paths are disjoint
    assert silver_a != silver_m
    a_paths = sorted(p.relative_to(silver_a) for p in silver_a.rglob("*") if p.is_file())
    m_paths = sorted(p.relative_to(silver_m) for p in silver_m.rglob("*") if p.is_file())
    assert a_paths and m_paths  # both wrote outputs


def test_rerun_anatomy_does_not_touch_microbiology(tmp_path: Path) -> None:
    """Archival of anatomy must not affect microbiology subdirectory."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    in_dir = _stage_anatomy(tmp_path / "in")
    _stage_microbiology(in_dir)
    out_dir = tmp_path / "out"

    base = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B"}),
        input_root=in_dir,
        output_root=out_dir,
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    run_needs_map(base)
    run_needs_map(base.model_copy(update={"course_slug": "microbiology"}))

    silver_m = out_dir / "silver" / "needs-map" / "2026-1-microbiology"
    micro_snapshot = {
        p.relative_to(silver_m): p.read_bytes()
        for p in silver_m.rglob("*")
        if p.is_file()
    }

    # Re-run anatomy
    run_needs_map(base)

    # microbiology files MUST be unchanged
    for rel, blob in micro_snapshot.items():
        target = silver_m / rel
        assert target.is_file()
        assert target.read_bytes() == blob, f"microbiology {rel} touched by anatomy rerun"


def test_canonical_keys_reject_malformed(tmp_path: Path) -> None:
    """SemesterCode + CourseSlug Pydantic validators reject malformed combinations early."""
    import pytest
    from needs_map.pipeline import NeedsMapArgs
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        NeedsMapArgs(
            semester="2026-Q1",  # not in SemesterCode pattern
            course_slug="anatomy",
            phases=frozenset({"A"}),
            input_root=tmp_path,
            output_root=tmp_path,
            seed=42,
            llm_enabled=False,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
        )
    with pytest.raises(ValidationError):
        NeedsMapArgs(
            semester="2026-1",
            course_slug="ANATOMY",  # uppercase rejected by CourseSlug pattern
            phases=frozenset({"A"}),
            input_root=tmp_path,
            output_root=tmp_path,
            seed=42,
            llm_enabled=False,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
        )
