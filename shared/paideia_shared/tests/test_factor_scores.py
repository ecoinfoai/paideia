"""Contract tests for FactorScoreRow validators (T036, M4)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas import FactorScoreRow
from pydantic import ValidationError

_AXES = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def _row(**overrides: object) -> FactorScoreRow:
    base: dict[str, object] = {
        "student_id": "2026194042",
        "on_roster": True,
        "responded": True,
        "section": "A",
    }
    for axis in _AXES:
        base[axis] = 4.0
        base[f"{axis}_z"] = 0.5
        base[f"{axis}_missing"] = False
    base.update(overrides)
    return FactorScoreRow(**base)  # type: ignore[arg-type]


# --- V1: score / zscore nullness must agree ---


def test_v1_score_and_zscore_both_float_passes() -> None:
    row = _row(motivation=5.0, motivation_z=1.2)
    assert row.motivation == 5.0
    assert row.motivation_z == 1.2


def test_v1_score_none_zscore_none_passes() -> None:
    row = _row(motivation=None, motivation_z=None, motivation_missing=True)
    assert row.motivation is None
    assert row.motivation_z is None


def test_v1_score_none_zscore_float_rejected() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(motivation=None, motivation_z=0.5, motivation_missing=True)


def test_v1_score_float_zscore_none_rejected() -> None:
    with pytest.raises(ValidationError, match="V1"):
        _row(motivation=4.0, motivation_z=None)


@pytest.mark.parametrize("axis", _AXES)
def test_v1_each_axis_independently_validated(axis: str) -> None:
    overrides = {axis: None, f"{axis}_z": 0.5, f"{axis}_missing": True}
    with pytest.raises(ValidationError, match="V1"):
        _row(**overrides)


# --- V2: missing flag True → score must be None ---


def test_v2_drop_policy_score_none_missing_true_passes() -> None:
    row = _row(motivation=None, motivation_z=None, motivation_missing=True)
    assert row.motivation_missing is True


def test_v2_mean_impute_score_float_missing_false_passes() -> None:
    """Imputed score recorded as missing=False — adversary H-1 invariant."""
    row = _row(motivation=4.0, motivation_z=0.5, motivation_missing=False)
    assert row.motivation == 4.0
    assert row.motivation_missing is False


def test_v2_missing_true_with_score_set_rejected() -> None:
    with pytest.raises(ValidationError, match="V2"):
        _row(motivation=4.0, motivation_z=0.5, motivation_missing=True)


# --- off-roster respondents may have section=None ---


def test_off_roster_respondent_section_none_allowed() -> None:
    row = _row(on_roster=False, responded=True, section=None)
    assert row.on_roster is False
    assert row.section is None


# --- contract integrity: extra fields forbidden ---


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError, match="extra"):
        _row(unknown_field="x")
