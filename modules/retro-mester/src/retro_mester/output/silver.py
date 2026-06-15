"""T025 — Silver-layer parquet writer for retro-mester.

Writes two parquet files into ``silver_path``:
- ``빈틈표.parquet``   — one row per UnitGap, sorted by (chapter, segment).
- ``변경권고.parquet`` — one row per ChangeRecommendation, sorted by (rank, chapter).

Dict columns (``cause_signals``) and list columns
(``cohort_failing_item_types``) are JSON-serialised to strings before
``to_parquet`` so pyarrow can encode them as plain UTF-8.

Determinism:
- Stable row order (chapter ASC, segment ASC; rank ASC NULLS-LAST for recs).
- ``json.dumps(sort_keys=True, ensure_ascii=False)`` for consistent key order.
- ``parquet_write_options()`` disables dictionary pages and statistics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from paideia_shared.schemas.change_recommendation import ChangeRecommendation
from paideia_shared.schemas.unit_gap import UnitGap

from retro_mester.output.determinism import parquet_write_options

_GAP_SORT_KEYS = ["chapter", "segment"]


def _dumps(obj: Any) -> str:  # noqa: ANN401
    """Serialize ``obj`` to a deterministic JSON string.

    Args:
        obj: A dict or list (the two column types that need encoding).

    Returns:
        Compact JSON string with sorted keys and Unicode preserved.
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _gap_to_dict(gap: UnitGap) -> dict[str, Any]:
    """Convert UnitGap to a flat dict, JSON-encoding complex columns.

    Args:
        gap: A UnitGap instance.

    Returns:
        Dict suitable for a pandas DataFrame row.
    """
    row = gap.model_dump()
    row["cause_signals"] = _dumps(row["cause_signals"])
    row["cohort_failing_item_types"] = _dumps(row["cohort_failing_item_types"])
    return row


def _rec_to_dict(rec: ChangeRecommendation) -> dict[str, Any]:
    """Convert ChangeRecommendation to a flat dict.

    Args:
        rec: A ChangeRecommendation instance.

    Returns:
        Dict suitable for a pandas DataFrame row.
    """
    return rec.model_dump()


def write_silver(
    gaps: list[UnitGap],
    recs: list[ChangeRecommendation],
    silver_path: Path,
) -> None:
    """Write ``빈틈표.parquet`` and ``변경권고.parquet`` to ``silver_path``.

    The caller is responsible for creating ``silver_path`` beforehand.
    Dict/list columns are JSON-serialised to strings so pyarrow writes
    plain UTF-8 without nested-type handling.  Row order is stable:
    gaps are sorted by (chapter, segment); recs by (rank_sort, chapter,
    segment) where ``None`` ranks sort last.

    Args:
        gaps: List of UnitGap records to write.
        recs: List of ChangeRecommendation records to write.
        silver_path: Target directory that must already exist.

    Raises:
        FileNotFoundError: When ``silver_path`` does not exist.
    """
    silver_path = Path(silver_path)
    if not silver_path.is_dir():
        raise FileNotFoundError(
            f"write_silver: directory missing: {silver_path}"
        )

    write_opts = parquet_write_options()

    # --- 빈틈표.parquet ---
    if gaps:
        df_gaps = pd.DataFrame([_gap_to_dict(g) for g in gaps])
        df_gaps = df_gaps.sort_values(by=_GAP_SORT_KEYS, ignore_index=True)
    else:
        # Empty but schema-consistent dataframe
        df_gaps = pd.DataFrame(columns=list(UnitGap.model_fields.keys()))
    table_gaps = pa.Table.from_pandas(df_gaps, preserve_index=False)
    pq.write_table(table_gaps, silver_path / "빈틈표.parquet", **write_opts)

    # --- 변경권고.parquet ---
    if recs:
        df_recs = pd.DataFrame([_rec_to_dict(r) for r in recs])
        # Sort by rank (None last) then chapter, segment for determinism
        df_recs["_rank_sort"] = df_recs["rank"].apply(
            lambda r: r if r is not None else 999
        )
        df_recs = df_recs.sort_values(
            by=["_rank_sort", "chapter", "segment"], ignore_index=True
        )
        df_recs = df_recs.drop(columns=["_rank_sort"])
    else:
        df_recs = pd.DataFrame(columns=list(ChangeRecommendation.model_fields.keys()))
    table_recs = pa.Table.from_pandas(df_recs, preserve_index=False)
    pq.write_table(table_recs, silver_path / "변경권고.parquet", **write_opts)


__all__ = ["write_silver"]
