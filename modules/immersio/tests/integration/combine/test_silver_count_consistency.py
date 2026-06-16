"""Integration test — silver row count vs manifest count consistency (T022, US3).

Asserts that ``n_students_combined`` in the rebuilt
``CombinedAnalysisManifest`` equals the actual parquet row count, and
that the four R-10 unmatched audit fields produced by the joiner survive
into the manifest writer's output verbatim.

Composition exercised: joiner → silver_writer → (counts +
compute_input_sha256) → CombinedAnalysisManifest → serialize_manifest_json
→ JSON re-load → row-count cross-check.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pyarrow.parquet as pq
import pytest
from immersio.combine.joiner import join_silver_phase3
from immersio.combine.manifest import (
    compute_input_sha256,
    serialize_manifest_json,
)
from immersio.combine.silver_writer import write_combined_silver
from paideia_shared.schemas.combined_analysis_manifest import (
    CombinedAnalysisManifest,
)


def _load_builder() -> ModuleType:
    here = Path(__file__).resolve()
    builder_path = here.parents[2] / "fixtures" / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location("build_silver_phase3", builder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_pipe(fixture_root: Path, silver_out: Path) -> tuple:
    nm = fixture_root / "silver" / "needs-map" / "2026-1-anatomy"
    im = fixture_root / "silver" / "immersio" / "2026-1-anatomy"
    cluster_names_raw = json.loads((nm / "cluster_names.json").read_text(encoding="utf-8"))
    cluster_names = {int(k): v for k, v in cluster_names_raw.items()}

    df, counts = join_silver_phase3(
        student_master=pq.read_table(im / "student_master.parquet").to_pandas(),
        factor_scores=pq.read_table(nm / "factor_scores.parquet").to_pandas(),
        cluster_assignment=pq.read_table(nm / "cluster_assignment.parquet").to_pandas(),
        cluster_names=cluster_names,
        student_metrics=pq.read_table(im / "학생지표.parquet").to_pandas(),
        diagnostic_response=pq.read_table(im / "diagnostic_response.parquet").to_pandas(),
    )
    write_combined_silver(df, silver_out)
    return df, counts, nm, im


def _build_manifest(
    df,
    counts,
    *,
    nm_dir: Path,
    im_dir: Path,
) -> CombinedAnalysisManifest:
    n_dx = int(((df["진단응답"]) & (~df["시험응시"])).sum())
    n_ex = int(((~df["진단응답"]) & (df["시험응시"])).sum())
    n_both = int(((df["진단응답"]) & (df["시험응시"])).sum())
    n_neither = int(((~df["진단응답"]) & (~df["시험응시"])).sum())
    return CombinedAnalysisManifest(
        schema_version="0.1.0",
        module_version="immersio/0.1.0",
        semester="2026-1",
        course_slug="anatomy",
        generated_at_utc="2026-04-30T00:00:00Z",
        factor_scores_sha256=compute_input_sha256(nm_dir / "factor_scores.parquet"),
        cluster_assignment_sha256=compute_input_sha256(nm_dir / "cluster_assignment.parquet"),
        cluster_names_sha256=compute_input_sha256(nm_dir / "cluster_names.json"),
        student_metrics_sha256=compute_input_sha256(im_dir / "학생지표.parquet"),
        student_master_sha256=compute_input_sha256(im_dir / "student_master.parquet"),
        diagnostic_response_sha256=compute_input_sha256(im_dir / "diagnostic_response.parquet"),
        n_students_combined=len(df),
        n_diagnostic_only=n_dx,
        n_exam_only=n_ex,
        n_both=n_both,
        n_neither=n_neither,
        n_unmatched_factor_scores=counts.unmatched_factor_scores,
        n_unmatched_cluster_assignment=counts.unmatched_cluster_assignment,
        n_unmatched_student_metrics=counts.unmatched_student_metrics,
        n_off_roster_respondents=counts.off_roster_respondents,
        ruleset_version="0.1.0",
        regression_method="OLS",
        multiple_comparison_method="BH-FDR",
        posthoc_method_used="Games_Howell",
        run_seed=0,
        needs_map_schema_version="1.1.0",
        immersio_phase2_schema_version="0.1.0",
        top3_predictor_axes=[],
    )


def test_manifest_n_students_combined_matches_parquet_rowcount(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """V1 invariant validated end-to-end on the minimal fixture."""
    builder = _load_builder()
    root = tmp_path_factory.mktemp("count_consistency")
    builder.build_silver_phase3_minimal(root)
    silver = root / "진단×시험결합.parquet"
    df, counts, nm, im = _run_pipe(root, silver)
    manifest = _build_manifest(df, counts, nm_dir=nm, im_dir=im)

    parquet_rows = pq.read_table(silver).num_rows
    assert manifest.n_students_combined == parquet_rows == 30


def test_manifest_partition_sums_to_total(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Manifest V1 — only/both/neither sum equals n_students_combined."""
    builder = _load_builder()
    root = tmp_path_factory.mktemp("count_partition")
    builder.build_silver_phase3_minimal(root)
    silver = root / "진단×시험결합.parquet"
    df, counts, nm, im = _run_pipe(root, silver)
    manifest = _build_manifest(df, counts, nm_dir=nm, im_dir=im)

    s = manifest.n_diagnostic_only + manifest.n_exam_only + manifest.n_both + manifest.n_neither
    assert s == manifest.n_students_combined


def test_minimal_fixture_partition_distribution(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Minimal: 22 응답+응시 + 5 응시-only + 3 응답-only + 0 neither = 30."""
    builder = _load_builder()
    root = tmp_path_factory.mktemp("count_distribution")
    builder.build_silver_phase3_minimal(root)
    silver = root / "진단×시험결합.parquet"
    df, counts, nm, im = _run_pipe(root, silver)
    manifest = _build_manifest(df, counts, nm_dir=nm, im_dir=im)

    assert manifest.n_both == 22  # 응답+응시
    assert manifest.n_exam_only == 5  # 응시-only
    assert manifest.n_diagnostic_only == 3  # 응답-only (결시)
    assert manifest.n_neither == 0


def test_unmatched_audit_fields_propagate(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """R-10: joiner UnmatchedCounts → manifest 4 unmatched fields verbatim."""
    builder = _load_builder()
    root = tmp_path_factory.mktemp("unmatched_propagate")
    builder.build_silver_phase3_minimal(root)
    silver = root / "진단×시험결합.parquet"
    df, counts, nm, im = _run_pipe(root, silver)
    manifest = _build_manifest(df, counts, nm_dir=nm, im_dir=im)

    assert manifest.n_unmatched_factor_scores == counts.unmatched_factor_scores
    assert manifest.n_unmatched_cluster_assignment == counts.unmatched_cluster_assignment
    assert manifest.n_unmatched_student_metrics == counts.unmatched_student_metrics
    assert manifest.n_off_roster_respondents == counts.off_roster_respondents
    # Minimal fixture has 0 unmatched across the board.
    assert manifest.n_unmatched_factor_scores == 0
    assert manifest.n_unmatched_cluster_assignment == 0
    assert manifest.n_unmatched_student_metrics == 0
    assert manifest.n_off_roster_respondents == 0


def test_manifest_serializes_with_canonical_form(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Manifest JSON survives serialize → re-load → key set check."""
    builder = _load_builder()
    root = tmp_path_factory.mktemp("count_serialize")
    builder.build_silver_phase3_minimal(root)
    silver = root / "진단×시험결합.parquet"
    df, counts, nm, im = _run_pipe(root, silver)
    manifest = _build_manifest(df, counts, nm_dir=nm, im_dir=im)
    text = serialize_manifest_json(manifest)
    payload = json.loads(text)
    # All 6 sha256 + 4 R-10 + 5 partition counts must round-trip.
    for key in (
        "factor_scores_sha256",
        "cluster_assignment_sha256",
        "cluster_names_sha256",
        "student_metrics_sha256",
        "student_master_sha256",
        "diagnostic_response_sha256",
        "n_unmatched_factor_scores",
        "n_unmatched_cluster_assignment",
        "n_unmatched_student_metrics",
        "n_off_roster_respondents",
        "n_students_combined",
        "n_diagnostic_only",
        "n_exam_only",
        "n_both",
        "n_neither",
    ):
        assert key in payload, f"manifest JSON missing required key {key!r}"
