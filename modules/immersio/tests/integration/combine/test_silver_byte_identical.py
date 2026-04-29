"""Integration test — silver `진단×시험결합.parquet` byte-identical re-run (T021, US3).

Drives the full joiner → silver_writer pipe twice on the same fixture
and asserts the produced parquet files are byte-for-byte equal. This
catches regressions in any of the three determinism vectors (#1 dict
JSON, #2 pyarrow flags, #6 row order) at the integration boundary.

T020 unit tests verify each vector in isolation; this integration test
verifies the *composition* — joiner + writer together preserve
determinism end-to-end.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pyarrow.parquet as pq
import pytest

from immersio.combine.joiner import join_silver_phase3
from immersio.combine.silver_writer import write_combined_silver


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


def _run_pipe(*, fixture_root: Path, output: Path) -> None:
    nm = fixture_root / "silver" / "needs-map" / "2026-1-anatomy"
    im = fixture_root / "silver" / "immersio" / "2026-1-anatomy"
    cluster_names_raw = json.loads(
        (nm / "cluster_names.json").read_text(encoding="utf-8")
    )
    cluster_names = {int(k): v for k, v in cluster_names_raw.items()}

    df, _ = join_silver_phase3(
        student_master=pq.read_table(im / "student_master.parquet").to_pandas(),
        factor_scores=pq.read_table(nm / "factor_scores.parquet").to_pandas(),
        cluster_assignment=pq.read_table(
            nm / "cluster_assignment.parquet"
        ).to_pandas(),
        cluster_names=cluster_names,
        student_metrics=pq.read_table(im / "학생지표.parquet").to_pandas(),
        diagnostic_response=pq.read_table(
            im / "diagnostic_response.parquet"
        ).to_pandas(),
    )
    write_combined_silver(df, output)


def test_full_pipe_byte_identical(tmp_path_factory: pytest.TempPathFactory) -> None:
    """joiner → silver_writer twice on the minimal fixture → byte-equal parquets."""
    builder = _load_builder()

    # Two independent fixture trees so we also catch any non-deterministic
    # state held by the builder itself.
    root1 = tmp_path_factory.mktemp("byte_identical_run1")
    root2 = tmp_path_factory.mktemp("byte_identical_run2")
    builder.build_silver_phase3_minimal(root1)
    builder.build_silver_phase3_minimal(root2)

    out1 = root1 / "진단×시험결합.parquet"
    out2 = root2 / "진단×시험결합.parquet"
    _run_pipe(fixture_root=root1, output=out1)
    _run_pipe(fixture_root=root2, output=out2)

    bytes1 = out1.read_bytes()
    bytes2 = out2.read_bytes()
    assert bytes1 == bytes2, (
        f"byte-identical violation — len(run1)={len(bytes1)}, "
        f"len(run2)={len(bytes2)}"
    )


def test_same_input_two_writes_byte_identical(
    tmp_path_factory: pytest.TempPathFactory, tmp_path: Path
) -> None:
    """Run pipe once, then write the same DataFrame twice — bytes equal."""
    builder = _load_builder()
    root = tmp_path_factory.mktemp("byte_identical_same_input")
    builder.build_silver_phase3_minimal(root)

    nm = root / "silver" / "needs-map" / "2026-1-anatomy"
    im = root / "silver" / "immersio" / "2026-1-anatomy"
    cluster_names_raw = json.loads(
        (nm / "cluster_names.json").read_text(encoding="utf-8")
    )
    cluster_names = {int(k): v for k, v in cluster_names_raw.items()}

    df, _ = join_silver_phase3(
        student_master=pq.read_table(im / "student_master.parquet").to_pandas(),
        factor_scores=pq.read_table(nm / "factor_scores.parquet").to_pandas(),
        cluster_assignment=pq.read_table(
            nm / "cluster_assignment.parquet"
        ).to_pandas(),
        cluster_names=cluster_names,
        student_metrics=pq.read_table(im / "학생지표.parquet").to_pandas(),
        diagnostic_response=pq.read_table(
            im / "diagnostic_response.parquet"
        ).to_pandas(),
    )

    out1 = tmp_path / "twice1.parquet"
    out2 = tmp_path / "twice2.parquet"
    write_combined_silver(df, out1)
    write_combined_silver(df, out2)
    assert out1.read_bytes() == out2.read_bytes()
