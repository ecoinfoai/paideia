"""Atomic write of the four Silver Parquets and the manifest sidecar."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from paideia_shared.schemas import (
    DiagnosticResponse,
    ExamItem,
    ExamResult,
    IngestManifest,
    StudentMaster,
)


_STUDENT_MASTER_COLUMNS: list[str] = [
    "student_id",
    "semester",
    "course_slug",
    "on_roster",
    "section",
    "name_kr",
    "diagnostic_responded",
    "exam_taken",
    "exam_absent",
    "attendance_recorded",
    "exam_total_score",
    "exam_max_score",
    "attendance_present_count",
    "attendance_absent_count",
    "attendance_late_count",
    "attendance_excused_count",
    "axis_scores",
]

_DIAGNOSTIC_RESPONSE_COLUMNS: list[str] = [
    "student_id",
    "semester",
    "course_slug",
    "axis",
    "axis_kind",
    "option_key",
    "value_int",
    "value_bool",
    "value_text",
    "source_column",
]

_EXAM_RESULT_COLUMNS: list[str] = [
    "student_id",
    "semester",
    "course_slug",
    "item_no",
    "response",
    "is_correct",
    "score",
]

_EXAM_ITEM_COLUMNS: list[str] = [
    "semester",
    "course_slug",
    "item_no",
    "chapter",
    "source",
    "expected_difficulty",
    "bloom",
    "answer_key",
    "points",
    "text",
    "distractors",
]


def _student_master_table(rows: list[StudentMaster]) -> pa.Table:
    records = []
    axis_keys: set[str] = set()
    for master in rows:
        axis_keys.update(master.axis_scores.keys())
    sorted_axis_keys = sorted(axis_keys)
    for master in sorted(rows, key=lambda m: m.student_id):
        record = master.model_dump()
        # Render axis_scores as a struct with deterministic key order
        struct_value = {key: record["axis_scores"].get(key) for key in sorted_axis_keys}
        record["axis_scores"] = struct_value
        records.append(record)
    df = pd.DataFrame.from_records(records, columns=_STUDENT_MASTER_COLUMNS)
    schema = pa.schema(
        [
            ("student_id", pa.string()),
            ("semester", pa.string()),
            ("course_slug", pa.string()),
            ("on_roster", pa.bool_()),
            ("section", pa.string()),
            ("name_kr", pa.string()),
            ("diagnostic_responded", pa.bool_()),
            ("exam_taken", pa.bool_()),
            ("exam_absent", pa.bool_()),
            ("attendance_recorded", pa.bool_()),
            ("exam_total_score", pa.float64()),
            ("exam_max_score", pa.float64()),
            ("attendance_present_count", pa.int64()),
            ("attendance_absent_count", pa.int64()),
            ("attendance_late_count", pa.int64()),
            ("attendance_excused_count", pa.int64()),
            (
                "axis_scores",
                pa.struct([(key, pa.float64()) for key in sorted_axis_keys]),
            ),
        ]
    )
    return pa.Table.from_pandas(df, schema=schema, preserve_index=False)


def _diagnostic_response_table(rows: list[DiagnosticResponse]) -> pa.Table:
    sorted_rows = sorted(
        rows,
        key=lambda r: (r.student_id, r.axis, r.option_key or "", r.source_column),
    )
    records = [row.model_dump() for row in sorted_rows]
    df = pd.DataFrame.from_records(records, columns=_DIAGNOSTIC_RESPONSE_COLUMNS)
    schema = pa.schema(
        [
            ("student_id", pa.string()),
            ("semester", pa.string()),
            ("course_slug", pa.string()),
            ("axis", pa.string()),
            ("axis_kind", pa.string()),
            ("option_key", pa.string()),
            ("value_int", pa.int64()),
            ("value_bool", pa.bool_()),
            ("value_text", pa.string()),
            ("source_column", pa.string()),
        ]
    )
    return pa.Table.from_pandas(df, schema=schema, preserve_index=False)


def _exam_result_table(rows: list[ExamResult]) -> pa.Table:
    sorted_rows = sorted(rows, key=lambda r: (r.student_id, r.item_no))
    records = [row.model_dump() for row in sorted_rows]
    df = pd.DataFrame.from_records(records, columns=_EXAM_RESULT_COLUMNS)
    schema = pa.schema(
        [
            ("student_id", pa.string()),
            ("semester", pa.string()),
            ("course_slug", pa.string()),
            ("item_no", pa.int64()),
            ("response", pa.string()),
            ("is_correct", pa.bool_()),
            ("score", pa.float64()),
        ]
    )
    return pa.Table.from_pandas(df, schema=schema, preserve_index=False)


def _exam_item_table(rows: list[ExamItem]) -> pa.Table:
    sorted_rows = sorted(rows, key=lambda r: r.item_no)
    records = [row.model_dump() for row in sorted_rows]
    df = pd.DataFrame.from_records(records, columns=_EXAM_ITEM_COLUMNS)
    schema = pa.schema(
        [
            ("semester", pa.string()),
            ("course_slug", pa.string()),
            ("item_no", pa.int64()),
            ("chapter", pa.string()),
            ("source", pa.string()),
            ("expected_difficulty", pa.string()),
            ("bloom", pa.string()),
            ("answer_key", pa.string()),
            ("points", pa.float64()),
            ("text", pa.string()),
            ("distractors", pa.list_(pa.string())),
        ]
    )
    return pa.Table.from_pandas(df, schema=schema, preserve_index=False)


def _write_parquet(table: pa.Table, target: Path) -> None:
    pq.write_table(
        table,
        target,
        compression="snappy",
        use_dictionary=False,
        write_statistics=False,
        store_schema=True,
    )


def write_silver(
    out_dir: Path,
    masters: list[StudentMaster],
    diag: list[DiagnosticResponse],
    exam: list[ExamResult],
    items: list[ExamItem],
    manifest: IngestManifest,
) -> None:
    """Atomically write the four Silver Parquets and manifest.json.

    Writes go to a temporary sibling directory and are renamed into place
    only after every artefact succeeds. Pre-existing outputs in ``out_dir``
    are removed only after the temporary directory is fully built.

    Args:
        out_dir: Target directory (e.g. data/silver/immersio/2026-1-anatomy).
        masters: List of StudentMaster rows.
        diag: List of DiagnosticResponse rows.
        exam: List of ExamResult rows.
        items: List of ExamItem rows.
        manifest: Validated IngestManifest sidecar.

    Raises:
        TypeError: If out_dir is not a pathlib.Path.
    """
    if not isinstance(out_dir, Path):
        raise TypeError(f"write_silver: expected Path, got {type(out_dir).__name__}.")

    out_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=f".{out_dir.name}-tmp-", dir=str(out_dir.parent)
    ) as tmp:
        tmp_dir = Path(tmp)
        _write_parquet(_student_master_table(masters), tmp_dir / "student_master.parquet")
        _write_parquet(
            _diagnostic_response_table(diag), tmp_dir / "diagnostic_response.parquet"
        )
        _write_parquet(_exam_result_table(exam), tmp_dir / "exam_result.parquet")
        _write_parquet(_exam_item_table(items), tmp_dir / "exam_item.parquet")
        manifest_payload = manifest.model_dump(mode="json")
        (tmp_dir / "manifest.json").write_text(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if out_dir.exists():
            shutil.rmtree(out_dir)
        # Move into place atomically; final destination is fresh.
        shutil.move(str(tmp_dir), str(out_dir))
        # NOTE: Python's TemporaryDirectory will attempt cleanup of the now-moved
        # path; we shield by recreating an empty dir at the original tmp location.
        Path(tmp).mkdir(exist_ok=True)
