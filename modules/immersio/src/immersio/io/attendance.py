"""Attendance XLSX parser conforming to the immersio standard template."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..ingest.errors import DuplicateStudentIdError
from ..normalize import normalize_student_id

EXPECTED_HEADER: tuple[str, ...] = (
    ("학번", "이름")
    + tuple(f"W{week:02d}" for week in range(1, 17))
    + ("비고",)
)
ALLOWED_CODES: frozenset[str] = frozenset({"O", "X", "L", "E"})

WEEK_COLUMNS: tuple[str, ...] = tuple(f"W{week:02d}" for week in range(1, 17))


def parse_attendance_xlsx(path: Path) -> pd.DataFrame:
    """Parse the attendance XLSX into a per-student summary DataFrame.

    Args:
        path: Path to the attendance XLSX file.

    Returns:
        DataFrame with columns:
            student_id, name_kr, attendance_present_count,
            attendance_absent_count, attendance_late_count,
            attendance_excused_count

    Raises:
        TypeError: If path is not a pathlib.Path.
        FileNotFoundError: If the file is missing.
        ValueError: If header layout, vocabulary, or student_id rules are violated.
    """
    if not isinstance(path, Path):
        raise TypeError(f"parse_attendance_xlsx: expected Path, got {type(path).__name__}.")

    raw = pd.read_excel(path, sheet_name=0, engine="openpyxl", dtype=object, header=None)
    if raw.empty:
        raise ValueError(f"parse_attendance_xlsx: empty workbook at {path}.")

    header_row = [str(value) if value is not None else "" for value in raw.iloc[0].tolist()]
    if tuple(header_row) != EXPECTED_HEADER:
        raise ValueError(
            f"parse_attendance_xlsx: header mismatch in {path}. "
            f"expected {list(EXPECTED_HEADER)}, found {header_row}."
        )

    body = raw.iloc[1:].copy()
    body.columns = list(EXPECTED_HEADER)
    body = body[body["학번"].notna()]

    records: list[dict] = []
    seen_ids: list[str] = []
    for _, row in body.iterrows():
        student_id = normalize_student_id(str(row["학번"]))
        if student_id in seen_ids:
            raise DuplicateStudentIdError(
                f"parse_attendance_xlsx: duplicate student_id {student_id!r} in {path}."
            )
        seen_ids.append(student_id)
        codes_upper: list[str] = []
        for col in WEEK_COLUMNS:
            cell = row[col]
            if cell is None or (isinstance(cell, float) and pd.isna(cell)) or cell == "":
                codes_upper.append("")
                continue
            code = str(cell).strip().upper()
            if code == "":
                codes_upper.append("")
                continue
            if code not in ALLOWED_CODES:
                raise ValueError(
                    f"parse_attendance_xlsx: unsupported attendance code {code!r} for "
                    f"student_id={student_id!r} in column {col} of {path}; expected one of "
                    f"{sorted(ALLOWED_CODES)} or blank."
                )
            codes_upper.append(code)
        records.append(
            {
                "student_id": student_id,
                "name_kr": (str(row["이름"]) if pd.notna(row["이름"]) else None),
                "attendance_present_count": codes_upper.count("O"),
                "attendance_absent_count": codes_upper.count("X"),
                "attendance_late_count": codes_upper.count("L"),
                "attendance_excused_count": codes_upper.count("E"),
            }
        )

    return pd.DataFrame.from_records(records).sort_values("student_id").reset_index(drop=True)
