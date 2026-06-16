"""Contract test — silver `진단×시험결합.parquet` 60-column schema (T018, US3).

Verifies that the joiner output (which silver_writer T020 will round-trip
through pyarrow) carries the 60 columns in the deterministic order
documented in ``contracts/parquet_silver_combined.md`` §Schema. Column
*existence* + *order* are the contract; per-row dtype/nullability is
covered by the Pydantic round-trip test (T019).

This test exists to catch contract drift: any change to the column
table must update both this test and the contract Markdown in lockstep.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pyarrow.parquet as pq
import pytest
from immersio.combine.joiner import join_silver_phase3
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS

_EXPECTED_COLUMNS_IN_ORDER: tuple[str, ...] = (
    # Group 1 — Identity (6)
    "student_id",
    "name_kr",
    "on_roster",
    "section",
    "semester",
    "course_slug",
    # Group 2 — needs-map factor_scores (24 = 8 axes × {raw, z, missing})
    *[f"{axis}_{suffix}" for axis in STANDARD_AXIS_KEYS for suffix in ("raw", "z", "missing")],
    # Group 3 — needs-map cluster (3)
    "cluster_id",
    "cluster_label",
    "cluster_distance",
    # Group 4 — immersio exam scores (6)
    "exam_taken",
    "total_score",
    "score_percent",
    "section_percentile",
    "cohort_percentile",
    "z_score",
    # Group 5 — immersio exam dict columns (7)
    "chapter_correct_rates",
    "source_correct_rates",
    "difficulty_correct_rates",
    "expected_difficulty_correct_rates",
    "item_type_correct_rates",
    "interest_chapters_correct_rate",
    "aversion_chapters_correct_rate",
    # Group 6 — needs-map auxiliary group columns (10)
    "prior_readiness_q5",
    "prior_readiness_q6",
    "time_pattern_q21",
    "time_pattern_q22",
    "time_pattern_q23",
    "interest_topics_q9",
    "interest_topics_q10",
    "interest_topics_q11",
    "categorical_intent_q12",
    "categorical_intent_q13",
    # Group 7 — combined metadata (4)
    "진단응답",
    "시험응시",
    "needs_map_schema_version",
    "immersio_phase2_schema_version",
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


@pytest.fixture(scope="module")
def joined_frame(tmp_path_factory: pytest.TempPathFactory) -> tuple:
    """Build minimal fixture, then run the joiner — yields the DataFrame."""
    out = tmp_path_factory.mktemp("silver_phase3_contract")
    builder = _load_builder()
    builder.build_silver_phase3_minimal(out)

    nm = out / "silver" / "needs-map" / "2026-1-anatomy"
    im = out / "silver" / "immersio" / "2026-1-anatomy"
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
    return df, counts


def test_column_count_is_exactly_60(joined_frame: tuple) -> None:
    df, _ = joined_frame
    assert len(df.columns) == 60, (
        f"contract drift: parquet_silver_combined.md fixes the column count at 60, "
        f"got {len(df.columns)}"
    )


def test_column_order_matches_contract(joined_frame: tuple) -> None:
    df, _ = joined_frame
    assert list(df.columns) == list(_EXPECTED_COLUMNS_IN_ORDER), (
        "column order drifted from contract (parquet_silver_combined.md)"
    )


def test_factor_score_block_is_24_columns_axis_grouped(
    joined_frame: tuple,
) -> None:
    """Per axis, raw → z → missing must be contiguous (3 columns, fixed order)."""
    df, _ = joined_frame
    for i, axis in enumerate(STANDARD_AXIS_KEYS):
        # Group 2 starts at index 6 (after Identity 6); 3 columns per axis.
        block_start = 6 + i * 3
        assert df.columns[block_start] == f"{axis}_raw"
        assert df.columns[block_start + 1] == f"{axis}_z"
        assert df.columns[block_start + 2] == f"{axis}_missing"


def test_combined_metadata_block_is_last_4_columns(joined_frame: tuple) -> None:
    df, _ = joined_frame
    assert list(df.columns[-4:]) == [
        "진단응답",
        "시험응시",
        "needs_map_schema_version",
        "immersio_phase2_schema_version",
    ]


def test_no_unexpected_columns(joined_frame: tuple) -> None:
    """Joiner must not leak the merge artefacts (e.g. ``responded`` from factor_scores)."""
    df, _ = joined_frame
    extras = set(df.columns) - set(_EXPECTED_COLUMNS_IN_ORDER)
    assert not extras, f"joiner leaked unexpected columns: {sorted(extras)}"
