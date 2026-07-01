"""Permission tests for cohort_filter writer functions (T007+T015).

RED → GREEN: verifies that write_cohort_silver and write_cohort_md produce
owner-only (0600) outputs. Uses the assert_owner_only fixture from conftest.
"""

from __future__ import annotations

from pathlib import Path

from immersio.email.cohort_filter import write_cohort_md, write_cohort_silver
from paideia_shared.schemas import CohortLabel, CohortRow


def _rows() -> list[CohortRow]:
    return [
        CohortRow(
            student_id="1234567001",
            name_kr="홍길동",
            score_percent=45.0,
            cohort=CohortLabel.LOW_SCORE,
        ),
        CohortRow(
            student_id="1234567002",
            name_kr="김갑동",
            score_percent=80.0,
            cohort=CohortLabel.REST,
        ),
    ]


def test_write_cohort_silver_is_owner_only(tmp_path: Path, assert_owner_only) -> None:
    """write_cohort_silver must produce a 0600 parquet (PII: student_id, name_kr)."""
    rows = [r for r in _rows() if r.cohort == CohortLabel.LOW_SCORE]
    dest = tmp_path / "silver" / "cohort_low.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    write_cohort_silver(rows, dest)
    assert_owner_only(dest)


def test_write_cohort_md_combined_is_owner_only(tmp_path: Path, assert_owner_only) -> None:
    """write_cohort_md combined output must be 0600 (PII: student_id, name_kr)."""
    low = [r for r in _rows() if r.cohort == CohortLabel.LOW_SCORE]
    rest = [r for r in _rows() if r.cohort == CohortLabel.REST]
    combined_path, _, _ = write_cohort_md(low, rest, tmp_path / "gold")
    assert_owner_only(combined_path)


def test_write_cohort_md_low_is_owner_only(tmp_path: Path, assert_owner_only) -> None:
    """write_cohort_md low-score output must be 0600."""
    low = [r for r in _rows() if r.cohort == CohortLabel.LOW_SCORE]
    rest = [r for r in _rows() if r.cohort == CohortLabel.REST]
    _, low_path, _ = write_cohort_md(low, rest, tmp_path / "gold")
    assert_owner_only(low_path)


def test_write_cohort_md_rest_is_owner_only(tmp_path: Path, assert_owner_only) -> None:
    """write_cohort_md rest output must be 0600."""
    low = [r for r in _rows() if r.cohort == CohortLabel.LOW_SCORE]
    rest = [r for r in _rows() if r.cohort == CohortLabel.REST]
    _, _, rest_path = write_cohort_md(low, rest, tmp_path / "gold")
    assert_owner_only(rest_path)
