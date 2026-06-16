"""Contract test — ``CombinedAnalysisRow`` Pydantic round-trip (T019, US3).

Verifies the read path that Phase 4 (라벨링) and retro-mester v0.2 will
exercise on the silver `진단×시험결합.parquet`:

    DataFrame (60 cols, dict columns native) →
    CombinedAnalysisRow.model_validate (per row) →
    model_dump (mode='python') round-trip equality

The byte-identical *parquet* round-trip half (read → write → read)
belongs to T021's integration test once silver_writer (T020) lands; this
contract test stays in-memory so it can land before silver_writer and
catch any joiner-side schema regressions early.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pyarrow.parquet as pq
import pytest
from immersio.combine.joiner import join_silver_phase3
from paideia_shared.schemas import CombinedAnalysisRow


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
def joined_records(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    out = tmp_path_factory.mktemp("silver_phase3_roundtrip")
    builder = _load_builder()
    builder.build_silver_phase3_minimal(out)

    nm = out / "silver" / "needs-map" / "2026-1-anatomy"
    im = out / "silver" / "immersio" / "2026-1-anatomy"
    cluster_names_raw = json.loads((nm / "cluster_names.json").read_text(encoding="utf-8"))
    cluster_names = {int(k): v for k, v in cluster_names_raw.items()}

    df, _ = join_silver_phase3(
        student_master=pq.read_table(im / "student_master.parquet").to_pandas(),
        factor_scores=pq.read_table(nm / "factor_scores.parquet").to_pandas(),
        cluster_assignment=pq.read_table(nm / "cluster_assignment.parquet").to_pandas(),
        cluster_names=cluster_names,
        student_metrics=pq.read_table(im / "학생지표.parquet").to_pandas(),
        diagnostic_response=pq.read_table(im / "diagnostic_response.parquet").to_pandas(),
    )
    return df.to_dict("records")


def test_every_row_validates_against_combined_analysis_row(
    joined_records: list[dict],
) -> None:
    """All 30 rows survive Pydantic V1-V6."""
    for record in joined_records:
        CombinedAnalysisRow.model_validate(record)


def test_round_trip_preserves_field_values(joined_records: list[dict]) -> None:
    """validate → model_dump must return the same data we put in (modulo defaults)."""
    for record in joined_records:
        row = CombinedAnalysisRow.model_validate(record)
        dumped = row.model_dump(mode="python")
        # Identity must survive untouched.
        assert dumped["student_id"] == record["student_id"]
        assert dumped["semester"] == record["semester"]
        assert dumped["course_slug"] == record["course_slug"]
        # Combined metadata must survive untouched.
        assert dumped["진단응답"] == record["진단응답"]
        assert dumped["시험응시"] == record["시험응시"]


def test_dict_columns_are_native_dicts_not_json_strings(
    joined_records: list[dict],
) -> None:
    """The contract is that joiner output exposes dicts, not JSON strings —
    silver_writer (T020) is responsible for JSON-encoding them on write."""
    record = joined_records[0]
    for col in (
        "chapter_correct_rates",
        "source_correct_rates",
        "difficulty_correct_rates",
        "expected_difficulty_correct_rates",
        "item_type_correct_rates",
    ):
        assert isinstance(record[col], dict), (
            f"{col} should be native dict at the joiner→writer boundary, "
            f"got {type(record[col]).__name__}"
        )


def test_dict_columns_json_encodable(joined_records: list[dict]) -> None:
    """T020 silver_writer will serialize via json.dumps(d, ensure_ascii=False,
    sort_keys=True) — the dict must be JSON-serializable now."""
    record = joined_records[0]
    for col in (
        "chapter_correct_rates",
        "source_correct_rates",
        "difficulty_correct_rates",
        "expected_difficulty_correct_rates",
        "item_type_correct_rates",
    ):
        # difficulty_correct_rates uses int keys; json.dumps handles that
        # only when the dict is naturally string-keyed *or* the int keys
        # round-trip to strings cleanly. The contract picks the latter.
        encoded = json.dumps(record[col], ensure_ascii=False, sort_keys=True)
        decoded = json.loads(encoded)
        assert isinstance(decoded, dict)


def test_axes_raw_z_missing_invariant(joined_records: list[dict]) -> None:
    """V2 invariant: per axis, raw is None ⇔ z is None ⇔ missing is True."""
    from paideia_shared.schemas._common import STANDARD_AXIS_KEYS

    for record in joined_records:
        for axis in STANDARD_AXIS_KEYS:
            raw = record[f"{axis}_raw"]
            z = record[f"{axis}_z"]
            missing = record[f"{axis}_missing"]
            assert (raw is None) == (z is None) == bool(missing)


def test_cluster_triple_invariant(joined_records: list[dict]) -> None:
    """V4: cluster_id / cluster_label / cluster_distance — all None or all set."""
    for record in joined_records:
        triple = (
            record["cluster_id"],
            record["cluster_label"],
            record["cluster_distance"],
        )
        none_count = sum(1 for v in triple if v is None)
        assert none_count in (0, 3), f"cluster triple inconsistent: {triple}"
