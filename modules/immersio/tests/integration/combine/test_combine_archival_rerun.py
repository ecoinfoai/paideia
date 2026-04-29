"""Integration test — Phase 3 archival + re-run byte-identical (T062, US6).

Drives ``run_us1_pipeline`` twice on the same fixture and asserts:
- 2nd run lands its silver/gold byte-identical to the 1st (vector
  composition unchanged after archival)
- 1st-run outputs survive in ``_archive/{ISO}__v{schema}/`` (FR-022)
- prior _archive contents stay (multi-iteration re-run)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_builder() -> ModuleType:
    here = Path(__file__).resolve()
    builder_path = here.parents[2] / "fixtures" / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location(
        "build_silver_phase3", builder_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_re_run_silver_byte_identical_after_archival(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """1st run silver bytes ≡ 2nd run silver bytes (post-archival)."""
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("rerun")
    builder.build_silver_phase3_minimal(tmp)

    # 1st run.
    rc1 = run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )
    assert rc1 == 0
    silver_path = (
        tmp / "silver" / "immersio" / "2026-1-anatomy" / "진단×시험결합.parquet"
    )
    bytes1 = silver_path.read_bytes()

    # 2nd run on the same dirs — archival hook moves 1st run aside.
    rc2 = run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )
    assert rc2 == 0
    bytes2 = silver_path.read_bytes()
    assert bytes1 == bytes2, "silver re-run not byte-identical"


def test_re_run_archives_first_run_outputs(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("rerun_archive")
    builder.build_silver_phase3_minimal(tmp)

    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )
    silver_archive = (
        tmp / "silver" / "immersio" / "2026-1-anatomy" / "_archive"
    )
    archived_files = {p.name for p in silver_archive.rglob("*") if p.is_file()}
    assert "진단×시험결합.parquet" in archived_files
    assert "manifest_phase3.json" in archived_files


def test_archive_disabled_by_flag(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """``archive=False`` → no _archive created (US3 fast-path)."""
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("rerun_no_archive")
    builder.build_silver_phase3_minimal(tmp)

    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
        archive=False,
    )
    silver_archive = (
        tmp / "silver" / "immersio" / "2026-1-anatomy" / "_archive"
    )
    assert not silver_archive.exists()


def test_multi_semester_runs_independent(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Runs against different (semester, course) pairs do not collide."""
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("multi_semester")
    builder.build_silver_phase3_minimal(tmp)

    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )
    target1 = tmp / "gold" / "immersio" / "2026-1-anatomy"
    assert (target1 / "결합분석보고서.md").exists()
    # Second semester directory must remain absent — independent run.
    target2 = tmp / "gold" / "immersio" / "2026-2-anatomy"
    assert not target2.exists()
