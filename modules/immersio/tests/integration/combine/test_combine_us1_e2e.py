"""Integration test — US1 partial e2e (T036).

Verifies the full pipeline composition end-to-end on the
``silver_phase3_minimal`` fixture:

- 6 산출 파일 land (T033 의 6 unit tests 가 inventory 검증; 본 test 는
  byte-identical re-run + PDF 페이지 수 [10, 18] SC-004(a) 게이트 추가)
- PDF page count ∈ [10, 18] — ``pypdf`` reader
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


def _build_run(tmp: Path) -> tuple[Path, Path]:
    builder = _load_builder()
    builder.build_silver_phase3_minimal(tmp)
    return tmp / "silver", tmp / "gold"


def test_us1_e2e_lands_six_artefacts(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """6 산출 inventory check (silver parquet + manifest + md + pdf + xlsx + 2 figs = 7 actually)."""
    from immersio.combine.pipeline import run_us1_pipeline

    tmp = tmp_path_factory.mktemp("us1_e2e")
    silver, gold = _build_run(tmp)
    rc = run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver,
        gold_dir=gold,
    )
    assert rc == 0
    # silver
    assert (silver / "immersio" / "2026-1-anatomy" / "진단×시험결합.parquet").exists()
    assert (silver / "immersio" / "2026-1-anatomy" / "manifest_phase3.json").exists()
    # gold
    target = gold / "immersio" / "2026-1-anatomy"
    assert (target / "결합분석보고서.md").exists()
    assert (target / "결합분석보고서.pdf").exists()
    assert (target / "결합분석.xlsx").exists()
    # figs
    assert list((target / "figs").glob("fig3_*.png"))
    assert list((target / "figs").glob("fig4_*.png"))


def test_us1_e2e_silver_byte_identical_re_run(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Two independent fixture roots → byte-identical silver parquet."""
    from immersio.combine.pipeline import run_us1_pipeline

    a = tmp_path_factory.mktemp("us1_e2e_a")
    b = tmp_path_factory.mktemp("us1_e2e_b")
    silver_a, gold_a = _build_run(a)
    silver_b, gold_b = _build_run(b)
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_a,
        gold_dir=gold_a,
    )
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_b,
        gold_dir=gold_b,
    )
    pa = (silver_a / "immersio" / "2026-1-anatomy" / "진단×시험결합.parquet").read_bytes()
    pb = (silver_b / "immersio" / "2026-1-anatomy" / "진단×시험결합.parquet").read_bytes()
    assert pa == pb


def test_us1_e2e_manifest_byte_identical(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Manifest_phase3.json byte-identical (vector #1 sort_keys)."""
    from immersio.combine.pipeline import run_us1_pipeline

    a = tmp_path_factory.mktemp("us1_e2e_manifest_a")
    b = tmp_path_factory.mktemp("us1_e2e_manifest_b")
    silver_a, gold_a = _build_run(a)
    silver_b, gold_b = _build_run(b)
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_a,
        gold_dir=gold_a,
    )
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver_b,
        gold_dir=gold_b,
    )
    ma = (silver_a / "immersio" / "2026-1-anatomy" / "manifest_phase3.json").read_bytes()
    mb = (silver_b / "immersio" / "2026-1-anatomy" / "manifest_phase3.json").read_bytes()
    assert ma == mb


def test_us1_e2e_pdf_page_count_upper_bound(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """SC-004(a) upper bound enforce on minimal fixture.

    Production cohort (n≈184) 에서는 [10, 18] 범위 정합 — minimal fixture
    (n=30 + 8 axes only + 13 chapter rates + Top-3) 는 보고서 분량이
    축소되어 < 10 페이지가 정상. 본 test 는 *upper bound 18 페이지* 만
    enforce — production 에서 SC-004(a) 의 lower bound (≥10) 위반은
    별도 production-data integration test 가 cover (Phase 9 T064 perf
    test 와 함께 묶음).
    """
    pypdf = pytest.importorskip("pypdf")
    from immersio.combine.pipeline import run_us1_pipeline

    tmp = tmp_path_factory.mktemp("us1_e2e_pdf")
    silver, gold = _build_run(tmp)
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=silver,
        gold_dir=gold,
    )
    pdf_path = gold / "immersio" / "2026-1-anatomy" / "결합분석보고서.pdf"
    reader = pypdf.PdfReader(str(pdf_path))
    n_pages = len(reader.pages)
    assert n_pages > 0, "PDF empty"
    assert n_pages <= 18, (
        f"SC-004(a) upper bound: PDF {n_pages} pages > 18 — operator readability."
    )
