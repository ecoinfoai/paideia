"""Diagnostic CSV parser with encoding fallback and student ID normalization."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Literal

import pandas as pd
from paideia_shared.schemas import DiagnosticMappingConfig

from ..ingest.errors import DuplicateStudentIdError
from ..normalize import normalize_student_id, read_text_with_fallback


def _identity_column(mapping: DiagnosticMappingConfig) -> str:
    for column in mapping.columns:
        if column.kind == "identity":
            return column.source
    raise ValueError("parse_diagnostic_csv: mapping has no identity column.")


def parse_diagnostic_csv(
    path: Path, mapping: DiagnosticMappingConfig
) -> tuple[pd.DataFrame, Literal["utf-8", "cp949"]]:
    """Parse a diagnostic CSV using the mapping's column declarations.

    Args:
        path: Path to the diagnostic CSV.
        mapping: DiagnosticMappingConfig describing column kinds and axes.

    Returns:
        Tuple ``(dataframe, encoding_label)``. ``dataframe`` is indexed by
        canonical student_id and contains the source-column subset declared
        in the mapping; ``encoding_label`` records the detected encoding
        for the ingest manifest.

    Raises:
        TypeError: If path is not a pathlib.Path.
        FileNotFoundError: If the CSV is missing.
        ValueError: If required columns are missing or student_id duplicates exist.
    """
    if not isinstance(path, Path):
        raise TypeError(f"parse_diagnostic_csv: expected Path, got {type(path).__name__}.")

    text, encoding = read_text_with_fallback(path)
    raw_df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_values=[""])

    identity = _identity_column(mapping)
    required_columns = {column.source for column in mapping.columns}
    missing = sorted(required_columns - set(raw_df.columns))
    if missing:
        raise ValueError(
            f"parse_diagnostic_csv: mapping references columns absent from "
            f"{path}: {missing}; available columns={list(raw_df.columns)}."
        )

    raw_df = raw_df.loc[:, [c for c in raw_df.columns if c in required_columns]].copy()
    raw_df["__student_id__"] = raw_df[identity].apply(normalize_student_id)

    duplicate_ids = raw_df["__student_id__"].duplicated()
    if duplicate_ids.any():
        offenders = raw_df.loc[duplicate_ids, "__student_id__"].tolist()
        raise DuplicateStudentIdError(
            f"parse_diagnostic_csv: duplicate student_id values in {path}: "
            f"{sorted(set(offenders))}."
        )

    raw_df = raw_df.drop(columns=[identity])
    raw_df = raw_df.rename(columns={"__student_id__": "student_id"})
    raw_df = raw_df.set_index("student_id").sort_index()
    return raw_df, encoding
