"""Contract tests for CohortRow (T100a)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas import CohortLabel, CohortRow
from pydantic import ValidationError


def test_valid_low_score_row() -> None:
    row = CohortRow(
        student_id="1234567001",
        name_kr="홍길동",
        score_percent=45.5,
        cohort=CohortLabel.LOW_SCORE,
    )
    assert row.cohort == CohortLabel.LOW_SCORE
    assert row.score_percent == 45.5


def test_valid_rest_row() -> None:
    row = CohortRow(
        student_id="1234567002",
        name_kr="김갑동",
        score_percent=85.0,
        cohort=CohortLabel.REST,
    )
    assert row.cohort == CohortLabel.REST


def test_score_below_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        CohortRow(
            student_id="1234567001",
            name_kr="홍길동",
            score_percent=-1.0,
            cohort=CohortLabel.LOW_SCORE,
        )


def test_score_above_hundred_rejected() -> None:
    with pytest.raises(ValidationError):
        CohortRow(
            student_id="1234567001",
            name_kr="홍길동",
            score_percent=101.0,
            cohort=CohortLabel.REST,
        )


def test_cohort_all_rejected_for_parquet_row() -> None:
    """ALL is a CLI/log-default only — parquet rows must be LOW_SCORE/REST."""
    with pytest.raises(ValidationError, match="LOW_SCORE or REST"):
        CohortRow(
            student_id="1234567001",
            name_kr="홍길동",
            score_percent=50.0,
            cohort=CohortLabel.ALL,
        )


def test_student_id_must_be_ten_digits() -> None:
    with pytest.raises(ValidationError):
        CohortRow(
            student_id="123",
            name_kr="홍길동",
            score_percent=50.0,
            cohort=CohortLabel.LOW_SCORE,
        )


def test_name_kr_required() -> None:
    with pytest.raises(ValidationError):
        CohortRow(
            student_id="1234567001",
            name_kr="",
            score_percent=50.0,
            cohort=CohortLabel.LOW_SCORE,
        )


def test_round_trip_preserves_fields() -> None:
    row = CohortRow(
        student_id="1234567001",
        name_kr="홍길동",
        score_percent=59.9,
        cohort=CohortLabel.LOW_SCORE,
    )
    again = CohortRow.model_validate(row.model_dump(mode="json"))
    assert again == row


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        CohortRow(
            student_id="1234567001",
            name_kr="홍길동",
            score_percent=50.0,
            cohort=CohortLabel.LOW_SCORE,
            extra_field="leak",
        )
