"""TDD tests for ``combine.pipeline`` US1 partial orchestration (T033).

Verifies that ``run_us1_pipeline`` composes silver_writer + correlation +
regression + recommendations + figures + report_md + report_pdf +
xlsx_writer + manifest into the 9-artifact deliverable for the US1
partial mode (silver parquet + manifest_phase3 + md + pdf + xlsx + 2
figs).

US2 (T042) + US4 (T056) wiring extends this orchestrator to the full
phase mode; this test set covers the partial path.
"""

from __future__ import annotations

import importlib.util
import json
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


@pytest.fixture
def silver_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("pipeline_us1")
    builder = _load_builder()
    builder.build_silver_phase3_minimal(out)
    return out


def test_run_returns_zero_on_success(silver_root: Path, tmp_path: Path) -> None:
    """Happy path → exit 0 + 6 artefacts on disk."""
    from immersio.combine.pipeline import run_us1_pipeline

    rc = run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_root / "silver",
        gold_dir=tmp_path / "gold",
    )
    assert rc == 0


def test_run_lands_silver_parquet(silver_root: Path, tmp_path: Path) -> None:
    from immersio.combine.pipeline import run_us1_pipeline

    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_root / "silver",
        gold_dir=tmp_path / "gold",
    )
    silver_parquet = (
        silver_root / "silver" / "immersio" / "2026-1-anatomy" / "진단×시험결합.parquet"
    )
    assert silver_parquet.exists()
    assert silver_parquet.stat().st_size > 0


def test_run_lands_manifest_phase3(silver_root: Path, tmp_path: Path) -> None:
    from immersio.combine.pipeline import run_us1_pipeline

    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_root / "silver",
        gold_dir=tmp_path / "gold",
    )
    manifest_path = (
        silver_root
        / "silver"
        / "immersio"
        / "2026-1-anatomy"
        / "manifest_phase3.json"
    )
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    # n_students_combined must equal the fixture's 30 students.
    assert payload["n_students_combined"] == 30
    # 6 sha256 fields present (cluster_names_sha256 GAP-10 included).
    for key in (
        "factor_scores_sha256",
        "cluster_assignment_sha256",
        "cluster_names_sha256",
        "student_metrics_sha256",
        "student_master_sha256",
        "diagnostic_response_sha256",
    ):
        assert key in payload
        assert len(payload[key]) == 64


def test_run_lands_gold_artefacts(silver_root: Path, tmp_path: Path) -> None:
    from immersio.combine.pipeline import run_us1_pipeline

    gold = tmp_path / "gold"
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_root / "silver",
        gold_dir=gold,
    )
    target = gold / "immersio" / "2026-1-anatomy"
    assert (target / "결합분석보고서.md").exists()
    assert (target / "결합분석보고서.pdf").exists()
    assert (target / "결합분석.xlsx").exists()


def test_run_lands_two_figs(silver_root: Path, tmp_path: Path) -> None:
    """fig3 (correlation heatmap) + fig4 (regression β bar) — file glob."""
    from immersio.combine.pipeline import run_us1_pipeline

    gold = tmp_path / "gold"
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_root / "silver",
        gold_dir=gold,
    )
    figs_dir = gold / "immersio" / "2026-1-anatomy" / "figs"
    assert figs_dir.is_dir()
    fig3_matches = list(figs_dir.glob("fig3_*.png"))
    fig4_matches = list(figs_dir.glob("fig4_*.png"))
    assert fig3_matches, "fig3 PNG missing"
    assert fig4_matches, "fig4 PNG missing"


def test_run_byte_identical_silver(
    silver_root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """End-to-end byte-identical re-run on silver parquet (T021 invariant)."""
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    root2 = tmp_path_factory.mktemp("pipeline_us1_run2")
    builder.build_silver_phase3_minimal(root2)
    gold1 = tmp_path_factory.mktemp("gold1")
    gold2 = tmp_path_factory.mktemp("gold2")

    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_root / "silver",
        gold_dir=gold1,
    )
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=root2 / "silver",
        gold_dir=gold2,
    )
    s1 = (
        silver_root
        / "silver"
        / "immersio"
        / "2026-1-anatomy"
        / "진단×시험결합.parquet"
    ).read_bytes()
    s2 = (
        root2
        / "silver"
        / "immersio"
        / "2026-1-anatomy"
        / "진단×시험결합.parquet"
    ).read_bytes()
    assert s1 == s2
