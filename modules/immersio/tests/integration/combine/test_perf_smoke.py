"""Performance smoke test (T064, SC-003).

Production cohort target: ≤ 90s wall + ≤ 8GB peak. This smoke test runs
the minimal fixture (30 students) and asserts the wall budget is met
with a generous margin (10s) — a regression in Big-O behaviour will fail
this gate even on minimal fixtures.

Production-data perf test belongs to a separate scheduled run (Phase 9
ops doc) since CI fixtures may not exercise n=184.
"""

from __future__ import annotations

import importlib.util
import time
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


def test_minimal_fixture_pipeline_under_10s(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """SC-003 smoke: minimal fixture pipeline ≤ 10s wall (regression gate)."""
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("perf_smoke")
    builder.build_silver_phase3_minimal(tmp)

    t0 = time.monotonic()
    rc = run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
        include_cluster=True,
        include_subgroup=True,
    )
    elapsed = time.monotonic() - t0
    assert rc == 0
    assert elapsed < 10.0, (
        f"SC-003 smoke regression: minimal fixture pipeline took {elapsed:.2f}s "
        f"(>10s) — production cohort (n≈184) projection >>90s likely."
    )
