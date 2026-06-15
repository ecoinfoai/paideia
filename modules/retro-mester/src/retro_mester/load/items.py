"""T014: loader for silver `문항통계.parquet` → list[ItemStatistics].

`option_distribution` is stored as a JSON string (dict[int, float]) in
parquet; keys are deserialized from str to int before Pydantic validation.

Returns a (rows, mismatch_report) tuple so the pipeline can record chapter
set mismatches in the manifest without silently ignoring them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import pandas as pd
from pydantic import ValidationError

from paideia_shared.schemas import ItemStatistics

from .errors import InputError


class ChapterMismatchReport(TypedDict):
    """Chapter-set mismatch between 문항통계 and 진단×시험결합."""

    items_not_in_combined: list[str]
    """Chapters found in 문항통계 but absent from 진단×시험결합 chapter_correct_rates."""

    combined_not_in_items: list[str]
    """Chapters found in 진단×시험결합 but absent from 문항통계."""


def load_items(
    path: Path,
    combined_chapters: set[str] | None = None,
) -> tuple[list[ItemStatistics], ChapterMismatchReport]:
    """Load silver `문항통계.parquet` and validate every row.

    Args:
        path: Absolute path to the parquet file.
        combined_chapters: Optional set of chapter labels from CombinedAnalysisRow
            ``chapter_correct_rates`` keys.  When provided, a mismatch report
            is computed; when omitted, both mismatch lists are empty.

    Returns:
        A (rows, mismatch_report) tuple where ``rows`` is a list of validated
        ItemStatistics instances and ``mismatch_report`` is a
        ChapterMismatchReport dict.

    Raises:
        InputError: If the file does not exist, ``option_distribution`` JSON
            is malformed, or a row fails Pydantic validation.
    """
    if not path.exists():
        raise InputError(f"Item statistics parquet not found: {path}")

    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        raise InputError(f"Failed to read parquet {path}: {exc}") from exc

    rows: list[ItemStatistics] = []
    for idx, series in df.iterrows():
        row_dict: dict = series.to_dict()

        # option_distribution: JSON string → dict[int, float]. A null/empty
        # parquet cell deserializes to a float NaN (or None), never a str —
        # guard before json.loads so a missing column defaults to {}.
        raw_od = row_dict.get("option_distribution")
        if not isinstance(raw_od, str):
            # Covers None, float NaN, and any non-string scalar.
            row_dict["option_distribution"] = {}
        else:
            try:
                parsed = json.loads(raw_od)
                row_dict["option_distribution"] = {int(k): float(v) for k, v in parsed.items()}
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise InputError(
                    f"JSON decode failed in {path} row {idx} column 'option_distribution': {exc}"
                ) from exc

        try:
            rows.append(ItemStatistics.model_validate(row_dict))
        except ValidationError as exc:
            raise InputError(
                f"Validation failed in {path} row {idx}: {exc}"
            ) from exc

    # Compute chapter-set mismatch.
    item_chapters: set[str] = {r.chapter for r in rows}
    if combined_chapters is None:
        mismatch: ChapterMismatchReport = {
            "items_not_in_combined": [],
            "combined_not_in_items": [],
        }
    else:
        mismatch = {
            "items_not_in_combined": sorted(item_chapters - combined_chapters),
            "combined_not_in_items": sorted(combined_chapters - item_chapters),
        }

    return rows, mismatch


__all__ = ["load_items", "ChapterMismatchReport"]
