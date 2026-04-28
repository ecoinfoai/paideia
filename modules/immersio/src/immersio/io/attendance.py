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

# Roster-only header (research §R-08a, FR-027): 학과 OMR 명단 시트가 직접 출석
# 코드 없이 학번/이름/분반만 담은 형식. 본 분기에서는 attendance_count 컬럼 모두
# None 으로 채우고 section 컬럼을 추가 산출한다.
ROSTER_REQUIRED_COLUMNS: frozenset[str] = frozenset({"학번", "이름", "분반"})

OUTPUT_COLUMNS: tuple[str, ...] = (
    "student_id",
    "name_kr",
    "section",
    "attendance_present_count",
    "attendance_absent_count",
    "attendance_late_count",
    "attendance_excused_count",
)


def _detect_layout(header_row: list[str]) -> str:
    """Pick the attendance layout for the given header row.

    Returns:
        ``"w01_w16"`` when header matches the weekly-attendance template,
        ``"roster_only"`` when header contains 학번/이름/분반 (FR-027),
        ``""`` (empty) when neither matches.
    """
    if tuple(header_row) == EXPECTED_HEADER:
        return "w01_w16"
    if ROSTER_REQUIRED_COLUMNS.issubset(set(header_row)):
        return "roster_only"
    return ""


def _parse_w01_w16(raw: pd.DataFrame, path: Path) -> pd.DataFrame:
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
                "section": None,
                "attendance_present_count": codes_upper.count("O"),
                "attendance_absent_count": codes_upper.count("X"),
                "attendance_late_count": codes_upper.count("L"),
                "attendance_excused_count": codes_upper.count("E"),
            }
        )

    return (
        pd.DataFrame.from_records(records, columns=list(OUTPUT_COLUMNS))
        .sort_values("student_id")
        .reset_index(drop=True)
    )


def _parse_roster_only(raw: pd.DataFrame, header_row: list[str], path: Path) -> pd.DataFrame:
    body = raw.iloc[1:].copy()
    body.columns = header_row
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
        section_raw = row["분반"]
        if section_raw is None or (isinstance(section_raw, float) and pd.isna(section_raw)):
            section: str | None = None
        else:
            section = str(section_raw).strip() or None
        records.append(
            {
                "student_id": student_id,
                "name_kr": (str(row["이름"]) if pd.notna(row["이름"]) else None),
                "section": section,
                "attendance_present_count": None,
                "attendance_absent_count": None,
                "attendance_late_count": None,
                "attendance_excused_count": None,
            }
        )

    return (
        pd.DataFrame.from_records(records, columns=list(OUTPUT_COLUMNS))
        .sort_values("student_id")
        .reset_index(drop=True)
    )


def parse_attendance_xlsx(path: Path) -> pd.DataFrame:
    """Parse the attendance XLSX into a per-student summary DataFrame.

    Two header layouts are supported (research §R-08a, FR-027):

    1. Weekly attendance: ``("학번", "이름", W01..W16, "비고")`` — populates
       ``attendance_*_count`` columns from the per-week codes.
    2. Roster-only: header includes ``학번/이름/분반`` — used when the
       department's OMR namesheet ships without per-week codes. All
       ``attendance_*_count`` columns are ``None`` in this branch and the
       ``section`` column is populated.

    Args:
        path: Path to the attendance XLSX file.

    Returns:
        DataFrame with columns ``OUTPUT_COLUMNS``: ``student_id``, ``name_kr``,
        ``section``, ``attendance_present_count``, ``attendance_absent_count``,
        ``attendance_late_count``, ``attendance_excused_count``.

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
    layout = _detect_layout(header_row)
    if layout == "w01_w16":
        return _parse_w01_w16(raw, path)
    if layout == "roster_only":
        return _parse_roster_only(raw, header_row, path)
    raise ValueError(
        f"parse_attendance_xlsx: header mismatch in {path}. "
        f"expected {list(EXPECTED_HEADER)} (weekly) or columns including "
        f"{sorted(ROSTER_REQUIRED_COLUMNS)} (roster-only), found {header_row}."
    )
