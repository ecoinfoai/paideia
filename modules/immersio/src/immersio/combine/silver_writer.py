"""Deterministic silver `진단×시험결합.parquet` writer (T020, US3).

FR-014 / FR-015 / FR-030 + research §R13 determinism vectors:
- vector #1: dict columns serialised as canonical JSON
  (``ensure_ascii=False, sort_keys=True``)
- vector #2: pyarrow ``compression='snappy', use_dictionary=False,
  write_statistics=False`` — eliminates dictionary pages and per-column
  min/max statistics, both of which can drift across pyarrow versions
- vector #6: row order ``student_id`` ascending stable sort

The 60-column contract (``contracts/parquet_silver_combined.md``) is
enforced via :data:`_REQUIRED_COLUMNS`; missing any column raises a
ValueError so partial silver outputs never reach downstream consumers
(Constitution V "부분 산출 금지").

Public API:
- :func:`write_combined_silver` — DataFrame → parquet (joiner output is
  the canonical input shape)
- :func:`read_combined_silver` — parquet → DataFrame with dict columns
  decoded back to native dicts so callers (Phase 4 labelling,
  retro-mester v0.2) can ``CombinedAnalysisRow.model_validate`` directly
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from paideia_shared.io import atomic_write

from .joiner import _COMBINED_COLUMN_ORDER

_REQUIRED_COLUMNS: frozenset[str] = frozenset(_COMBINED_COLUMN_ORDER)

_DICT_COLUMNS: tuple[str, ...] = (
    "chapter_correct_rates",
    "source_correct_rates",
    "difficulty_correct_rates",
    "expected_difficulty_correct_rates",
    "item_type_correct_rates",
)


def _encode_dict_column(value: object) -> str:
    """Canonical JSON encoding of a dict column value.

    Empty / missing values normalise to ``"{}"`` so the parquet column
    has uniform string dtype (no nullable string mix).
    """
    if value is None:
        return "{}"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, float):
        # NaN sentinel from upstream merge → empty dict.
        return "{}"
    if isinstance(value, str):
        # Already a JSON string (idempotent — re-canonicalise).
        if not value:
            return "{}"
        return json.dumps(json.loads(value), ensure_ascii=False, sort_keys=True)
    raise TypeError(
        f"silver_writer: unexpected dict column value type {type(value).__name__}: {value!r}"
    )


def write_combined_silver(df: pd.DataFrame, path: Path) -> None:
    """Write the 60-column joiner output to a deterministic parquet.

    Steps:
      1. Validate that every contract column is present (Fail-Fast).
      2. Encode the 5 dict columns as canonical JSON strings (vector #1).
      3. Sort rows by ``student_id`` ascending stable (vector #6).
      4. Reorder columns to the contract sequence.
      5. Write parquet with the determinism flags (vector #2).

    Args:
        df: Joiner output DataFrame (``join_silver_phase3`` return shape).
        path: Destination ``.parquet`` path. Parent directories are
            created on demand.

    Raises:
        ValueError: If any of the 60 contract columns is missing from
            ``df`` (Constitution V — silent partial output 차단).
    """
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"silver_writer: 60-column contract violation — input DataFrame "
            f"is missing columns {sorted(missing)}"
        )

    # architect (c) — 13 bool columns must never carry NaN. The joiner
    # builds them via fillna/직접 산출, but a manual mutation upstream could
    # break this contract; explicit Fail-Fast surfaces the anomaly before
    # parquet land.
    bool_columns = (
        "on_roster",
        "exam_taken",
        "진단응답",
        "시험응시",
        *(
            f"{axis}_missing"
            for axis in (
                "digital_efficacy",
                "motivation",
                "time_availability",
                "material_preference",
                "study_strategy",
                "study_environment",
                "social_learning",
                "feedback_seeking",
            )
        ),
    )
    for col in bool_columns:
        if df[col].isna().any():
            raise ValueError(
                f"silver_writer: bool column {col!r} carries NaN — pipeline "
                f"anomaly (Constitution III + architect Phase 3 위협 (c))"
            )

    out = df.copy()
    for col in _DICT_COLUMNS:
        out[col] = out[col].map(_encode_dict_column)

    out = out.sort_values("student_id", ascending=True, kind="stable").reset_index(drop=True)
    out = out[list(_COMBINED_COLUMN_ORDER)]

    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(out, preserve_index=False)
    atomic_write(
        path,
        lambda p: pq.write_table(
            table,
            p,
            compression="snappy",
            use_dictionary=False,
            write_statistics=False,
        ),
    )


def read_combined_silver(path: Path) -> pd.DataFrame:
    """Read a Phase 3 silver parquet and decode dict columns to native dicts.

    Inverse of :func:`write_combined_silver` for callers that immediately
    feed rows into ``CombinedAnalysisRow.model_validate`` (Phase 4
    labelling, retro-mester v0.2). Pandas NaN sentinels are converted to
    ``None`` so Pydantic V2 ``Optional`` fields accept the values.
    """
    df = pq.read_table(path).to_pandas()
    for col in _DICT_COLUMNS:
        df[col] = df[col].map(lambda v: json.loads(v) if isinstance(v, str) and v else {})
    # NaN → None for the remaining (non-dict) columns so downstream Pydantic
    # validation accepts them. Mirrors the joiner's post-merge cleanup.
    non_dict_cols = [c for c in df.columns if c not in _DICT_COLUMNS]
    for col in non_dict_cols:
        df[col] = df[col].astype(object).where(df[col].notna(), None)
    return df


__all__ = ["read_combined_silver", "write_combined_silver"]
