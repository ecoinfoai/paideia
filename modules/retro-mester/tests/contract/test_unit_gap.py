"""Contract tests for UnitGap (M2, T006).

RED → GREEN: written before schema; ensure each invariant fires a ValidationError
and a valid construction succeeds.
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import UnitGap
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_kwargs() -> dict:
    return {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "chapter": "8장 호흡계통",
        "segment": "만학도",
        "segment_mean_rate": 0.52,
        "n_below": 8,
        "pct_segment": 0.53,
        "pct_cohort": 0.40,
        "is_structural": True,
        "cohort_failing_item_types": ["선다형", "빈칸채우기"],
        "cause": "내용난이도",
        "cause_signals": {"item_difficulty_mean": 0.35, "topic_complexity": 0.8},
        "validity": "건전",
        "unit_importance": "상",
        "weight": 3.0,
        "impact_score": 24.0,  # 8 * 3.0
        "evidence_n": 15,
    }


# ---------------------------------------------------------------------------
# Valid construction
# ---------------------------------------------------------------------------


def test_valid_construction() -> None:
    """A fully specified valid UnitGap is accepted."""
    gap = UnitGap(**_valid_kwargs())
    assert gap.chapter == "8장 호흡계통"
    assert gap.impact_score == 24.0
    assert gap.is_structural is True


# ---------------------------------------------------------------------------
# V1: n_below <= evidence_n
# ---------------------------------------------------------------------------


def test_v1_n_below_exceeds_evidence_n() -> None:
    """V1: n_below > evidence_n raises ValidationError."""
    kw = _valid_kwargs()
    kw["n_below"] = 20  # > evidence_n=15
    with pytest.raises(ValidationError, match="V1"):
        UnitGap(**kw)


def test_v1_n_below_equals_evidence_n_accepted() -> None:
    """V1: n_below == evidence_n is accepted (all measured students are below)."""
    kw = _valid_kwargs()
    kw["n_below"] = 15
    kw["impact_score"] = 15 * 3.0  # keep V2 happy
    gap = UnitGap(**kw)
    assert gap.n_below == gap.evidence_n


# ---------------------------------------------------------------------------
# V2: impact_score == n_below * weight
# ---------------------------------------------------------------------------


def test_v2_impact_score_mismatch() -> None:
    """V2: impact_score != n_below * weight raises ValidationError."""
    kw = _valid_kwargs()
    kw["impact_score"] = 99.0  # should be 8 * 3.0 = 24.0
    with pytest.raises(ValidationError, match="V2"):
        UnitGap(**kw)


def test_v2_impact_score_within_float_tolerance() -> None:
    """V2: floating-point values within 1e-6 of n_below*weight are accepted."""
    kw = _valid_kwargs()
    kw["n_below"] = 3
    kw["weight"] = 1.0 / 3.0
    kw["impact_score"] = 1.0  # 3 * (1/3) has fp noise; within 1e-6
    kw["evidence_n"] = 15
    gap = UnitGap(**kw)
    assert gap.n_below == 3


# ---------------------------------------------------------------------------
# Extra-field rejection
# ---------------------------------------------------------------------------


def test_extra_field_rejected() -> None:
    """extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        UnitGap(**_valid_kwargs(), unknown_field="bad")


# ---------------------------------------------------------------------------
# Frozen
# ---------------------------------------------------------------------------


def test_frozen_prevents_mutation() -> None:
    """frozen=True prevents in-place attribute mutation."""
    gap = UnitGap(**_valid_kwargs())
    with pytest.raises(Exception):
        gap.cause = "미상"  # type: ignore[misc]
