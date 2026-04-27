"""Contract tests for ScaleReliabilityRow + ScaleReliabilityReport (T035, M3)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas import (
    ScaleReliabilityReport,
    ScaleReliabilityRow,
)
from pydantic import ValidationError


def _row(**overrides: object) -> ScaleReliabilityRow:
    base: dict[str, object] = {
        "axis_key": "motivation",
        "n_items": 4,
        "cronbach_alpha": 0.85,
        "label": "computed",
        "operational_warning": False,
    }
    base.update(overrides)
    return ScaleReliabilityRow(**base)  # type: ignore[arg-type]


# --- V1 label/n_items/alpha consistency ---


def test_no_items_label_with_alpha_none() -> None:
    row = _row(n_items=0, cronbach_alpha=None, label="no_items")
    assert row.label == "no_items"
    assert row.cronbach_alpha is None


def test_no_items_label_rejects_non_none_alpha() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(n_items=0, cronbach_alpha=0.5, label="no_items")


def test_no_items_count_requires_no_items_label() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(n_items=0, cronbach_alpha=None, label="single_item")


@pytest.mark.parametrize("n_items", [1, 2])
def test_single_item_label_when_n_items_below_three(n_items: int) -> None:
    row = _row(n_items=n_items, cronbach_alpha=None, label="single_item")
    assert row.cronbach_alpha is None
    assert row.label == "single_item"


def test_single_item_rejects_non_none_alpha() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(n_items=2, cronbach_alpha=0.5, label="single_item")


def test_n_items_below_three_rejects_computed_label() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(n_items=2, cronbach_alpha=0.5, label="computed")


def test_computed_label_requires_alpha() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(n_items=4, cronbach_alpha=None, label="computed")


def test_not_applicable_label_requires_alpha_none() -> None:
    row = _row(n_items=4, cronbach_alpha=None, label="not_applicable")
    assert row.label == "not_applicable"


def test_not_applicable_with_alpha_rejected() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(n_items=4, cronbach_alpha=0.5, label="not_applicable")


def test_n_items_three_or_more_rejects_no_items_label() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(n_items=4, cronbach_alpha=None, label="no_items")


# --- V2 operational_warning semantics (FR-005) ---


def test_operational_warning_true_when_alpha_below_0_7() -> None:
    row = _row(cronbach_alpha=0.65, operational_warning=True)
    assert row.operational_warning is True


def test_operational_warning_requires_label_computed() -> None:
    with pytest.raises(ValidationError, match="V2"):
        _row(
            n_items=2,
            cronbach_alpha=None,
            label="single_item",
            operational_warning=True,
        )


def test_operational_warning_requires_alpha_below_0_7() -> None:
    with pytest.raises(ValidationError, match="V2"):
        _row(cronbach_alpha=0.85, operational_warning=True)


def test_operational_warning_false_with_high_alpha() -> None:
    row = _row(cronbach_alpha=0.92, operational_warning=False)
    assert row.operational_warning is False


# --- ScaleReliabilityReport V1 (no duplicate axis_key) ---


def test_report_accepts_unique_axis_rows() -> None:
    report = ScaleReliabilityReport(
        rows=[
            _row(axis_key="motivation"),
            _row(axis_key="study_strategy", cronbach_alpha=0.78),
        ],
        semester="2026-1",
        course_slug="anatomy",
        module_version="needs-map/0.1.0",
    )
    assert len(report.rows) == 2


def test_report_rejects_duplicate_axis_key() -> None:
    with pytest.raises(ValidationError, match="ScaleReliabilityReport V1"):
        ScaleReliabilityReport(
            rows=[
                _row(axis_key="motivation"),
                _row(axis_key="motivation", cronbach_alpha=0.65),
            ],
            semester="2026-1",
            course_slug="anatomy",
            module_version="needs-map/0.1.0",
        )


def test_report_accepts_empty_rows() -> None:
    report = ScaleReliabilityReport(
        rows=[],
        semester="2026-1",
        course_slug="anatomy",
        module_version="needs-map/0.1.0",
    )
    assert report.rows == []
