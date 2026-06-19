"""Contract tests for RetroMesterConfig (M1, T005).

RED → GREEN: written before schema; ensure each invariant fires a ValidationError
and a valid construction succeeds.
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import RetroMesterConfig
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_kwargs() -> dict:
    return {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "group_roster": {
            "2026194001": "학령기",
            "2026194002": "만학도",
        },
        "unit_importance": {
            "8장 호흡계통": "상",
            "9장 소화계통": "중",
        },
    }


# ---------------------------------------------------------------------------
# Valid construction
# ---------------------------------------------------------------------------


def test_valid_construction_with_defaults() -> None:
    """A minimal valid config uses schema defaults for optional fields."""
    cfg = RetroMesterConfig(**_valid_kwargs())
    assert cfg.semester == "2026-1"
    assert cfg.course_slug == "anatomy"
    assert cfg.gap_threshold == 0.6
    assert cfg.baseline_segment == "만학도"
    assert cfg.importance_weights == {"상": 3.0, "중": 2.0, "하": 1.0}
    assert cfg.effort_ratings == {}
    assert cfg.prior_readiness_low_labels == []


def test_valid_construction_explicit_overrides() -> None:
    """Explicit overrides for all fields are accepted."""
    cfg = RetroMesterConfig(
        **_valid_kwargs(),
        importance_weights={"상": 4.0, "중": 2.0, "하": 1.0},
        gap_threshold=0.75,
        baseline_segment="학령기",
        low_discrimination_threshold=0.3,
        cognitive_cliff_drop=0.2,
        effort_ratings={"8장 호흡계통": "상"},
        prior_readiness_low_labels=["낮음", "매우낮음"],
    )
    assert cfg.gap_threshold == 0.75
    assert cfg.baseline_segment == "학령기"
    assert cfg.effort_ratings == {"8장 호흡계통": "상"}
    assert cfg.prior_readiness_low_labels == ["낮음", "매우낮음"]


def test_prior_readiness_low_labels_default_is_empty_and_isolated() -> None:
    """prior_readiness_low_labels defaults to [] and is not shared across instances."""
    cfg_a = RetroMesterConfig(**_valid_kwargs())
    cfg_b = RetroMesterConfig(**_valid_kwargs())
    assert cfg_a.prior_readiness_low_labels == []
    # default_factory must yield a distinct list per instance (no shared mutable).
    assert cfg_a.prior_readiness_low_labels is not cfg_b.prior_readiness_low_labels


# ---------------------------------------------------------------------------
# V1: gap_threshold range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.01, 1.01, -1.0, 2.5])
def test_v1_gap_threshold_out_of_range(bad: float) -> None:
    """V1: gap_threshold outside [0, 1] raises ValidationError."""
    with pytest.raises(ValidationError, match="V1"):
        RetroMesterConfig(**_valid_kwargs(), gap_threshold=bad)


def test_v1_gap_threshold_boundary_0() -> None:
    """V1: gap_threshold=0.0 is accepted."""
    cfg = RetroMesterConfig(**_valid_kwargs(), gap_threshold=0.0)
    assert cfg.gap_threshold == 0.0


def test_v1_gap_threshold_boundary_1() -> None:
    """V1: gap_threshold=1.0 is accepted."""
    cfg = RetroMesterConfig(**_valid_kwargs(), gap_threshold=1.0)
    assert cfg.gap_threshold == 1.0


# ---------------------------------------------------------------------------
# V2: low_discrimination_threshold non-negative
# ---------------------------------------------------------------------------


def test_v2_low_discrimination_negative() -> None:
    """V2: negative low_discrimination_threshold raises ValidationError."""
    with pytest.raises(ValidationError, match="V2"):
        RetroMesterConfig(**_valid_kwargs(), low_discrimination_threshold=-0.01)


# ---------------------------------------------------------------------------
# V3: cognitive_cliff_drop non-negative
# ---------------------------------------------------------------------------


def test_v3_cognitive_cliff_negative() -> None:
    """V3: negative cognitive_cliff_drop raises ValidationError."""
    with pytest.raises(ValidationError, match="V3"):
        RetroMesterConfig(**_valid_kwargs(), cognitive_cliff_drop=-0.1)


# ---------------------------------------------------------------------------
# V4: importance_weights keys
# ---------------------------------------------------------------------------


def test_v4_importance_weights_missing_key() -> None:
    """V4: importance_weights with a missing key raises ValidationError."""
    with pytest.raises(ValidationError, match="V4"):
        RetroMesterConfig(
            **_valid_kwargs(),
            importance_weights={"상": 3.0, "중": 2.0},  # missing 하
        )


def test_v4_importance_weights_extra_key() -> None:
    """V4: importance_weights with an extra key raises ValidationError.

    Note: Pydantic rejects the invalid Literal key before the model_validator
    fires, so the match is on the general ValidationError, not 'V4'.
    """
    with pytest.raises(ValidationError):
        RetroMesterConfig(
            **_valid_kwargs(),
            importance_weights={"상": 3.0, "중": 2.0, "하": 1.0, "극상": 5.0},
        )


# ---------------------------------------------------------------------------
# Extra-field rejection
# ---------------------------------------------------------------------------


def test_extra_field_rejected() -> None:
    """extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        RetroMesterConfig(**_valid_kwargs(), unknown_field="bad")


# ---------------------------------------------------------------------------
# Frozen (immutability)
# ---------------------------------------------------------------------------


def test_frozen_prevents_mutation() -> None:
    """frozen=True prevents in-place attribute mutation."""
    cfg = RetroMesterConfig(**_valid_kwargs())
    with pytest.raises(Exception):  # ValidationError or AttributeError
        cfg.gap_threshold = 0.9  # type: ignore[misc]
