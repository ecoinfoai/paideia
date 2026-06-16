"""cohort_filter.py unit tests (T100c)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from immersio.email.cohort_filter import (
    SCORE_THRESHOLD_PCT_100,
    CohortError,
    filter_by_cohort,
)
from paideia_shared.schemas import CohortLabel, EmailMappingEntry


def _entry(sid: str, idx: int = 0) -> EmailMappingEntry:
    return EmailMappingEntry(
        student_id=sid,
        email=f"student{idx}@example.com",
        source_row_index=idx,
        original_timestamp=datetime(2026, 5, 1, 9, 0, 0, tzinfo=UTC),
    )


def _write_metrics(
    tmp_path: Path,
    rows: list[tuple[str, str, float | None]],
) -> Path:
    """Write a 학생지표.parquet stub with student_id/name_kr/score_percent."""
    path = tmp_path / "학생지표.parquet"
    table = pa.table(
        {
            "student_id": [r[0] for r in rows],
            "name_kr": [r[1] for r in rows],
            "score_percent": [r[2] for r in rows],
        }
    )
    pq.write_table(table, path)
    return path


def test_score_below_threshold_lands_in_low(tmp_path: Path) -> None:
    metrics = _write_metrics(
        tmp_path,
        [
            ("1234567001", "홍길동", 45.0),
            ("1234567002", "김갑동", 80.0),
        ],
    )
    result = filter_by_cohort(
        [_entry("1234567001", 0), _entry("1234567002", 1)],
        metrics,
        CohortLabel.LOW_SCORE,
    )
    assert [r.student_id for r in result.low_rows] == ["1234567001"]
    assert [r.student_id for r in result.rest_rows] == ["1234567002"]
    # Only LOW_SCORE students kept for sending
    assert [e.student_id for e in result.keep_entries] == ["1234567001"]


def test_score_exactly_threshold_in_rest(tmp_path: Path) -> None:
    """Boundary: score == 60 → REST (FR-H03 strict ``<``)."""
    metrics = _write_metrics(
        tmp_path,
        [("1234567001", "홍길동", 60.0)],
    )
    result = filter_by_cohort([_entry("1234567001")], metrics, CohortLabel.ALL)
    assert result.low_rows == []
    assert [r.student_id for r in result.rest_rows] == ["1234567001"]


def test_score_none_unavailable(tmp_path: Path) -> None:
    """score_percent=None → unavailable_sids (excluded from both cohorts)."""
    metrics = _write_metrics(
        tmp_path,
        [
            ("1234567001", "홍길동", None),
            ("1234567002", "김갑동", 75.0),
        ],
    )
    result = filter_by_cohort(
        [_entry("1234567001"), _entry("1234567002")],
        metrics,
        CohortLabel.ALL,
    )
    assert result.low_rows == []
    assert [r.student_id for r in result.rest_rows] == ["1234567002"]
    assert result.unavailable_sids == ["1234567001"]
    # Unavailable student NOT in keep_entries
    assert "1234567001" not in [e.student_id for e in result.keep_entries]


def test_cohort_all_keeps_both_partitions(tmp_path: Path) -> None:
    metrics = _write_metrics(
        tmp_path,
        [
            ("1234567001", "홍길동", 45.0),
            ("1234567002", "김갑동", 80.0),
        ],
    )
    result = filter_by_cohort(
        [_entry("1234567001"), _entry("1234567002")],
        metrics,
        CohortLabel.ALL,
    )
    assert {e.student_id for e in result.keep_entries} == {
        "1234567001",
        "1234567002",
    }


def test_cohort_low_score_keeps_only_low(tmp_path: Path) -> None:
    metrics = _write_metrics(
        tmp_path,
        [
            ("1234567001", "홍길동", 45.0),
            ("1234567002", "김갑동", 80.0),
        ],
    )
    result = filter_by_cohort(
        [_entry("1234567001"), _entry("1234567002")],
        metrics,
        CohortLabel.LOW_SCORE,
    )
    assert [e.student_id for e in result.keep_entries] == ["1234567001"]


def test_cohort_rest_keeps_only_rest(tmp_path: Path) -> None:
    metrics = _write_metrics(
        tmp_path,
        [
            ("1234567001", "홍길동", 45.0),
            ("1234567002", "김갑동", 80.0),
        ],
    )
    result = filter_by_cohort(
        [_entry("1234567001"), _entry("1234567002")],
        metrics,
        CohortLabel.REST,
    )
    assert [e.student_id for e in result.keep_entries] == ["1234567002"]


def test_metrics_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(CohortError, match="FR-H02"):
        filter_by_cohort([_entry("1234567001")], tmp_path / "missing.parquet", CohortLabel.ALL)


def test_metrics_missing_columns_raises(tmp_path: Path) -> None:
    bad = tmp_path / "metrics.parquet"
    pq.write_table(
        pa.table({"student_id": ["1234567001"], "name_kr": ["홍길동"]}),
        bad,
    )
    with pytest.raises(CohortError, match="missing required columns"):
        filter_by_cohort([_entry("1234567001")], bad, CohortLabel.ALL)


def test_threshold_constant_is_sixty() -> None:
    """ADR-006: hard-coded operator policy threshold."""
    assert SCORE_THRESHOLD_PCT_100 == 60
