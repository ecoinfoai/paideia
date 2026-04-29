"""TDD tests for ``combine.silver_writer`` (T020, US3).

Verifies that ``write_combined_silver`` produces a byte-deterministic
60-column parquet matching ``contracts/parquet_silver_combined.md``:

- pyarrow flags ``compression='snappy', use_dictionary=False,
  write_statistics=False`` (research §R13 vector #2)
- dict columns serialised as JSON strings with
  ``json.dumps(value, ensure_ascii=False, sort_keys=True)`` (vector #1)
- row order ``student_id`` ascending (vector #6)
- two consecutive writes on the same DataFrame yield byte-identical files

The helper :func:`read_combined_silver` lifts dict columns back into
native dicts so callers (Phase 4 labelling, retro-mester v0.2) can
``CombinedAnalysisRow.model_validate`` the records directly.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pyarrow.parquet as pq
import pytest

from immersio.combine.joiner import join_silver_phase3
from immersio.combine.silver_writer import (
    read_combined_silver,
    write_combined_silver,
)
from paideia_shared.schemas import CombinedAnalysisRow


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


@pytest.fixture(scope="module")
def joined_df(tmp_path_factory: pytest.TempPathFactory) -> pd.DataFrame:
    out = tmp_path_factory.mktemp("silver_phase3_writer")
    builder = _load_builder()
    builder.build_silver_phase3_minimal(out)

    nm = out / "silver" / "needs-map" / "2026-1-anatomy"
    im = out / "silver" / "immersio" / "2026-1-anatomy"
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
    return df


# ---------------------------------------------------------------------------
# Round-trip + write
# ---------------------------------------------------------------------------


def test_write_creates_parquet_file(joined_df: pd.DataFrame, tmp_path: Path) -> None:
    out = tmp_path / "진단×시험결합.parquet"
    write_combined_silver(joined_df, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_written_parquet_has_60_columns(joined_df: pd.DataFrame, tmp_path: Path) -> None:
    out = tmp_path / "out.parquet"
    write_combined_silver(joined_df, out)
    table = pq.read_table(out)
    assert len(table.column_names) == 60


def test_written_parquet_row_count_matches(
    joined_df: pd.DataFrame, tmp_path: Path
) -> None:
    out = tmp_path / "out.parquet"
    write_combined_silver(joined_df, out)
    table = pq.read_table(out)
    assert table.num_rows == len(joined_df)


def test_read_combined_silver_decodes_dict_columns(
    joined_df: pd.DataFrame, tmp_path: Path
) -> None:
    """read_combined_silver lifts JSON-string dicts back into native dicts."""
    out = tmp_path / "out.parquet"
    write_combined_silver(joined_df, out)
    df = read_combined_silver(out)
    record = df.to_dict("records")[0]
    for col in (
        "chapter_correct_rates",
        "source_correct_rates",
        "difficulty_correct_rates",
        "expected_difficulty_correct_rates",
        "item_type_correct_rates",
    ):
        assert isinstance(record[col], dict), (
            f"{col} must be native dict after read, got {type(record[col]).__name__}"
        )


def test_round_trip_pydantic_validation(
    joined_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Every row survives Pydantic V1-V6 after parquet round-trip."""
    out = tmp_path / "out.parquet"
    write_combined_silver(joined_df, out)
    df = read_combined_silver(out)
    for record in df.to_dict("records"):
        CombinedAnalysisRow.model_validate(record)


# ---------------------------------------------------------------------------
# Determinism — vectors 1, 2, 6
# ---------------------------------------------------------------------------


def test_determinism_vector_2_pyarrow_flags(
    joined_df: pd.DataFrame, tmp_path: Path
) -> None:
    """research §R13 vector #2 — use_dictionary=False, write_statistics=False."""
    out = tmp_path / "out.parquet"
    write_combined_silver(joined_df, out)
    table_meta = pq.read_metadata(out)
    rg_meta = table_meta.row_group(0)
    for col_idx in range(rg_meta.num_columns):
        col_meta = rg_meta.column(col_idx)
        assert not col_meta.has_dictionary_page, (
            f"column {col_idx} has dictionary page (use_dictionary must be False)"
        )
        # Statistics may be present as a Statistics object but should hold no
        # min/max in the deterministic-write mode; we accept either no stats
        # or an empty stats stub.
        stats = col_meta.statistics
        if stats is not None:
            assert stats.min is None and stats.max is None, (
                f"column {col_idx} carries min/max stats "
                f"(write_statistics must be False)"
            )


def test_determinism_vector_6_row_order_student_id_ascending(
    joined_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Row sort student_id ascending — robust against pre-shuffled input."""
    shuffled = joined_df.sample(frac=1.0, random_state=42).reset_index(drop=True)
    out = tmp_path / "out.parquet"
    write_combined_silver(shuffled, out)
    table = pq.read_table(out).to_pandas()
    sids = table["student_id"].tolist()
    assert sids == sorted(sids)


def test_determinism_vector_1_dict_json_sort_keys(
    joined_df: pd.DataFrame, tmp_path: Path
) -> None:
    """dict columns serialised with sort_keys=True ensures byte-identical JSON."""
    out = tmp_path / "out.parquet"
    write_combined_silver(joined_df, out)
    table = pq.read_table(out).to_pandas()
    sample = table["chapter_correct_rates"].iloc[0]
    # Re-encode and require identity — sort_keys + ensure_ascii=False fixed.
    decoded = json.loads(sample)
    canonical = json.dumps(decoded, ensure_ascii=False, sort_keys=True)
    assert sample == canonical, (
        f"chapter_correct_rates JSON not canonical: got {sample!r}, "
        f"expected {canonical!r}"
    )


def test_byte_identical_two_consecutive_writes(
    joined_df: pd.DataFrame, tmp_path: Path
) -> None:
    """T021 의 integration 테스트가 본 invariant 에 의존."""
    out1 = tmp_path / "run1.parquet"
    out2 = tmp_path / "run2.parquet"
    write_combined_silver(joined_df, out1)
    write_combined_silver(joined_df, out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_dict_columns_stored_as_strings(
    joined_df: pd.DataFrame, tmp_path: Path
) -> None:
    """5 dict columns must land as parquet string type (R8 + contract §Group 5)."""
    out = tmp_path / "out.parquet"
    write_combined_silver(joined_df, out)
    schema = pq.read_schema(out)
    for col in (
        "chapter_correct_rates",
        "source_correct_rates",
        "difficulty_correct_rates",
        "expected_difficulty_correct_rates",
        "item_type_correct_rates",
    ):
        field = schema.field(col)
        assert "string" in str(field.type), (
            f"dict column {col} must be string-typed in parquet, "
            f"got {field.type}"
        )


def test_creates_parent_directory(joined_df: pd.DataFrame, tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nest" / "out.parquet"
    write_combined_silver(joined_df, nested)
    assert nested.exists()


def test_write_rejects_input_missing_required_columns(
    joined_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Fail-Fast: missing any of the 60 contract columns ⇒ ValueError."""
    bad = joined_df.drop(columns=["진단응답"])
    out = tmp_path / "bad.parquet"
    with pytest.raises(ValueError, match="60-column contract"):
        write_combined_silver(bad, out)
