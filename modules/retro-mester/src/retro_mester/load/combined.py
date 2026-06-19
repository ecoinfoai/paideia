"""T013: loader for silver `진단×시험결합.parquet` → list[CombinedAnalysisRow].

Dict columns are stored as JSON strings in parquet; this loader decodes them
and converts `difficulty_correct_rates` keys from str to int before validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from paideia_shared.schemas import CombinedAnalysisRow
from pydantic import ValidationError

from .errors import InputError

# Columns that are stored as JSON strings in parquet.
_JSON_COLS = (
    "chapter_correct_rates",
    "source_correct_rates",
    "difficulty_correct_rates",
    "expected_difficulty_correct_rates",
    "item_type_correct_rates",
)

# Nullable float columns whose absence carries semantic meaning (audit M2): a
# missing interest/aversion rate must round-trip to ``None``, not a float NaN.
# A missing parquet cell deserializes to NaN, which would otherwise pass the
# ``float | None`` schema as a (non-None) NaN and be miscounted as a present
# response.  Normalising NaN → None at this boundary keeps the cohort gap
# computation honest about insufficient data.
_NULLABLE_FLOAT_COLS = (
    "interest_chapters_correct_rate",
    "aversion_chapters_correct_rate",
)


def load_combined(path: Path) -> list[CombinedAnalysisRow]:
    """Load silver `진단×시험결합.parquet` and validate every row.

    Args:
        path: Absolute path to the parquet file.

    Returns:
        List of validated CombinedAnalysisRow instances (one per student).

    Raises:
        InputError: If the file does not exist, a JSON-dict column is
            malformed, or a row fails Pydantic validation.
    """
    if not path.exists():
        raise InputError(f"Combined analysis parquet not found: {path}")

    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        raise InputError(f"Failed to read parquet {path}: {exc}") from exc

    rows: list[CombinedAnalysisRow] = []
    for idx, series in df.iterrows():
        row_dict: dict = series.to_dict()

        # Decode JSON-string columns. A null/empty parquet cell deserializes
        # to a float NaN (or None), never a str — guard before json.loads so a
        # missing dict column defaults to {} instead of crashing.
        for col in _JSON_COLS:
            raw = row_dict.get(col)
            if not isinstance(raw, str):
                # Covers None, float NaN, and any non-string scalar.
                row_dict[col] = {}
                continue
            try:
                row_dict[col] = json.loads(raw)
            except (json.JSONDecodeError, TypeError) as exc:
                raise InputError(
                    f"JSON decode failed in {path} row {idx} column '{col}': {exc}"
                ) from exc

        # Normalise NaN → None for nullable float columns whose absence is
        # meaningful (audit M2).  pandas reads a null cell as float NaN.
        for col in _NULLABLE_FLOAT_COLS:
            val = row_dict.get(col)
            if isinstance(val, float) and pd.isna(val):
                row_dict[col] = None

        # difficulty_correct_rates: JSON gives str keys; schema wants int keys.
        dcr = row_dict.get("difficulty_correct_rates", {})
        if dcr:
            try:
                row_dict["difficulty_correct_rates"] = {int(k): v for k, v in dcr.items()}
            except (ValueError, TypeError) as exc:
                raise InputError(
                    f"Non-integer key in difficulty_correct_rates in {path} row {idx}: {exc}"
                ) from exc

        try:
            rows.append(CombinedAnalysisRow.model_validate(row_dict))
        except ValidationError as exc:
            raise InputError(f"Validation failed in {path} row {idx}: {exc}") from exc

    return rows


__all__ = ["load_combined"]
