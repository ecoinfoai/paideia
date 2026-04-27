"""Silver-layer parquet loaders for needs-map.

Reads ingest Phase 0 outputs (``DiagnosticResponse`` and ``StudentMaster`` Silver
parquets) into pandas DataFrames after sample-validating the first 100 rows
against the Pydantic contract. Full row-by-row validation happens at the parquet
write boundary in later phases (M3-M6 in data-model.md).

Spec FR-001: missing inputs / contract violations stop the analysis early with
the offending path included in the exception message.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from paideia_shared.schemas import DiagnosticResponse, StudentMaster

_SAMPLE_SIZE = 100


def _silver_dir(input_root: Path, semester: str, course: str) -> Path:
    """Resolve ``{input_root}/silver/immersio/{semester}-{course}/`` path."""
    return input_root / "silver" / "immersio" / f"{semester}-{course}"


def _read_parquet(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Silver input not found: {path}")
    return pd.read_parquet(path)


def _row_to_dict(row: pd.Series) -> dict:
    """Convert a DataFrame row to a dict with pandas NaN/NaT mapped to None.

    Parquet reads bring nullable string/Literal columns back as float-NaN when
    the column is sparsely populated; Pydantic Literal/str validators choke on
    NaN. Mapping NaN/NaT → None at the row boundary keeps the loader contract
    clean without polluting downstream code.
    """
    out: dict = {}
    for key, value in row.to_dict().items():
        if (isinstance(value, float) and pd.isna(value)) or value is pd.NaT:
            out[key] = None
        else:
            out[key] = value
    return out


def _validate_sample(
    df: pd.DataFrame, model: type, *, label: str, path: Path
) -> None:
    """Validate the first ``_SAMPLE_SIZE`` rows against ``model``.

    Raises ValueError(message including path) on first contract violation. Full
    row validation is deferred to write-time in pipeline.py to keep loader fast.
    """
    if df.empty:
        return
    sample = df.head(_SAMPLE_SIZE)
    for index, (_, row) in enumerate(sample.iterrows()):
        try:
            model.model_validate(_row_to_dict(row))
        except Exception as exc:
            raise ValueError(
                f"{label} contract violation at {path} row {index}: {exc}"
            ) from exc


def load_diagnostic_response(
    input_root: Path, semester: str, course: str
) -> pd.DataFrame:
    """Load ``diagnostic_response.parquet`` and sample-validate.

    Args:
        input_root: Project data root (typically ``./data``).
        semester: Semester code (e.g. ``"2026-1"``).
        course: Course slug (e.g. ``"anatomy"``).

    Returns:
        DataFrame with one row per (student, axis[, option_key]) entry.

    Raises:
        FileNotFoundError: If ``diagnostic_response.parquet`` is missing.
        ValueError: If any of the first ``_SAMPLE_SIZE`` rows fails Pydantic
            validation; message includes the file path and row index.
    """
    path = _silver_dir(input_root, semester, course) / "diagnostic_response.parquet"
    df = _read_parquet(path)
    _validate_sample(df, DiagnosticResponse, label="DiagnosticResponse", path=path)
    return df


def load_student_master(
    input_root: Path, semester: str, course: str
) -> pd.DataFrame:
    """Load ``student_master.parquet`` and sample-validate.

    Args:
        input_root: Project data root (typically ``./data``).
        semester: Semester code (e.g. ``"2026-1"``).
        course: Course slug (e.g. ``"anatomy"``).

    Returns:
        DataFrame with one row per student (roster + off-roster respondents).

    Raises:
        FileNotFoundError: If ``student_master.parquet`` is missing.
        ValueError: If any of the first ``_SAMPLE_SIZE`` rows fails Pydantic
            validation; message includes the file path and row index.
    """
    path = _silver_dir(input_root, semester, course) / "student_master.parquet"
    df = _read_parquet(path)
    _validate_sample(df, StudentMaster, label="StudentMaster", path=path)
    return df
