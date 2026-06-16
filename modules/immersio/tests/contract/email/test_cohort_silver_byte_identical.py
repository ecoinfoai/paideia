"""Cohort silver parquet byte-identical contract test (T100e)."""

from __future__ import annotations

from pathlib import Path

from immersio.email.cohort_filter import write_cohort_silver
from paideia_shared.schemas import CohortLabel, CohortRow


def _row(sid: str, score: float) -> CohortRow:
    return CohortRow(
        student_id=sid,
        name_kr="홍길동",
        score_percent=score,
        cohort=CohortLabel.LOW_SCORE,
    )


def test_two_writes_byte_identical(tmp_path: Path) -> None:
    rows = [_row("1234567001", 45.0), _row("1234567002", 50.0)]
    a = tmp_path / "a.parquet"
    b = tmp_path / "b.parquet"
    write_cohort_silver(rows, a)
    write_cohort_silver(rows, b)
    assert a.read_bytes() == b.read_bytes()


def test_byte_identical_ignores_call_order_when_input_sorted(
    tmp_path: Path,
) -> None:
    """Same sorted input → same bytes regardless of when written."""
    rows = [_row("1234567001", 45.0), _row("1234567002", 50.0)]
    a = tmp_path / "a.parquet"
    write_cohort_silver(rows, a)
    bytes_a = a.read_bytes()
    a.unlink()
    write_cohort_silver(rows, a)
    bytes_b = a.read_bytes()
    assert bytes_a == bytes_b
