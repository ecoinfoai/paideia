"""Phase A roster tests (T032)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from immersio.email.roster import (
    RosterError,
    load_email_mapping,
    write_mapping_silver,
)


_HEADER = ["타임스탬프", "사용자 이름", "학번"]


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_HEADER)
        writer.writerows(rows)


def test_basic_load_sorted_by_student_id(tmp_path: Path) -> None:
    csv_path = tmp_path / "bronze.csv"
    _write_csv(
        csv_path,
        [
            ["2026/03/03 11:03:36 AM GMT+9", "alice@example.com", "1234567002"],
            ["2026/03/03 11:04:39 AM GMT+9", "bob@example.com", "1234567001"],
        ],
    )
    entries = load_email_mapping(csv_path)
    assert [e.student_id for e in entries] == ["1234567001", "1234567002"]
    assert entries[0].email == "bob@example.com"


def test_zero_pad_9_digit_student_id_rejected(tmp_path: Path) -> None:
    """9-digit IDs are rejected (normalize_student_id raises ValueError)."""
    csv_path = tmp_path / "bronze.csv"
    _write_csv(
        csv_path,
        [
            ["2026/03/03 11:03:36 AM GMT+9", "alice@example.com", "202619400"],
        ],
    )
    entries = load_email_mapping(csv_path)
    assert entries == []


def test_invalid_email_skipped(tmp_path: Path) -> None:
    csv_path = tmp_path / "bronze.csv"
    _write_csv(
        csv_path,
        [
            ["2026/03/03 11:03:36 AM GMT+9", "not-an-email", "1234567001"],
            ["2026/03/03 11:04:39 AM GMT+9", "ok@example.com", "1234567002"],
        ],
    )
    entries = load_email_mapping(csv_path)
    assert [e.student_id for e in entries] == ["1234567002"]


def test_duplicate_student_id_keeps_first_response(tmp_path: Path) -> None:
    csv_path = tmp_path / "bronze.csv"
    _write_csv(
        csv_path,
        [
            ["2026/03/03 11:03:36 AM GMT+9", "first@example.com", "1234567001"],
            ["2026/03/03 11:04:39 AM GMT+9", "second@example.com", "1234567001"],
        ],
    )
    entries = load_email_mapping(csv_path)
    assert len(entries) == 1
    assert entries[0].email == "first@example.com"
    assert entries[0].source_row_index == 1


def test_email_lowercase_and_strip(tmp_path: Path) -> None:
    csv_path = tmp_path / "bronze.csv"
    _write_csv(
        csv_path,
        [
            ["2026/03/03 11:03:36 AM GMT+9", "  Alice@Example.COM  ", "1234567001"],
        ],
    )
    entries = load_email_mapping(csv_path)
    assert entries[0].email == "alice@example.com"


def test_source_row_index_preserved(tmp_path: Path) -> None:
    csv_path = tmp_path / "bronze.csv"
    _write_csv(
        csv_path,
        [
            ["2026/03/03 11:03:36 AM GMT+9", "alice@example.com", "1234567002"],
            ["2026/03/03 11:04:39 AM GMT+9", "bob@example.com", "1234567001"],
        ],
    )
    entries = load_email_mapping(csv_path)
    # Sorted by student_id, but source_row_index reflects original CSV order
    by_sid = {e.student_id: e for e in entries}
    assert by_sid["1234567002"].source_row_index == 1
    assert by_sid["1234567001"].source_row_index == 2


def test_missing_csv_raises(tmp_path: Path) -> None:
    with pytest.raises(RosterError, match="not found"):
        load_email_mapping(tmp_path / "nonexistent.csv")


def test_silver_parquet_byte_identical_two_runs(tmp_path: Path) -> None:
    csv_path = tmp_path / "bronze.csv"
    _write_csv(
        csv_path,
        [
            ["2026/03/03 11:03:36 AM GMT+9", "alice@example.com", "1234567001"],
            ["2026/03/03 11:04:39 AM GMT+9", "bob@example.com", "1234567002"],
        ],
    )
    entries = load_email_mapping(csv_path)
    silver_a = tmp_path / "a.parquet"
    silver_b = tmp_path / "b.parquet"
    write_mapping_silver(entries, silver_a)
    write_mapping_silver(entries, silver_b)
    assert silver_a.read_bytes() == silver_b.read_bytes()
