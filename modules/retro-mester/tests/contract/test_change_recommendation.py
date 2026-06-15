"""Contract tests for ChangeRecommendation (M3, T007).

RED → GREEN: written before schema; ensure each invariant fires a ValidationError
and a valid construction succeeds.
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import ChangeRecommendation
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _covered_kwargs() -> dict:
    return {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "rank": 1,
        "chapter": "8장 호흡계통",
        "target_cognitive_level": "이해",
        "segment": "만학도",
        "cause_hypothesis": "내용난이도",
        "covered_n": 8,
        "covered_pct_segment": 0.53,
        "covered_pct_cohort": 0.40,
        "unit_importance": "상",
        "weight": 3.0,
        "impact_score": 24.0,
        "effort_level": "중",
        "priority_quadrant": "빠른승리",
        "prescription_key": "scaffold_concepts",
        "cluster_vocab": None,
        "validity": "건전",
        "is_covered": True,
    }


def _uncovered_kwargs() -> dict:
    kw = _covered_kwargs()
    kw["rank"] = None
    kw["is_covered"] = False
    return kw


# ---------------------------------------------------------------------------
# Valid construction — covered
# ---------------------------------------------------------------------------

def test_valid_covered_recommendation() -> None:
    """A covered recommendation (rank 1-5, is_covered=True) is accepted."""
    rec = ChangeRecommendation(**_covered_kwargs())
    assert rec.rank == 1
    assert rec.is_covered is True


@pytest.mark.parametrize("rank", [1, 2, 3, 4, 5])
def test_valid_covered_all_ranks(rank: int) -> None:
    """All ranks 1-5 are valid for covered recommendations."""
    kw = _covered_kwargs()
    kw["rank"] = rank
    rec = ChangeRecommendation(**kw)
    assert rec.rank == rank


# ---------------------------------------------------------------------------
# Valid construction — uncovered
# ---------------------------------------------------------------------------

def test_valid_uncovered_recommendation() -> None:
    """An uncovered recommendation (rank=None, is_covered=False) is accepted."""
    rec = ChangeRecommendation(**_uncovered_kwargs())
    assert rec.rank is None
    assert rec.is_covered is False


# ---------------------------------------------------------------------------
# V1: is_covered=True ⇒ rank in [1,5]
# ---------------------------------------------------------------------------

def test_v1_covered_rank_none() -> None:
    """V1: is_covered=True with rank=None raises ValidationError."""
    kw = _covered_kwargs()
    kw["rank"] = None
    with pytest.raises(ValidationError, match="V1"):
        ChangeRecommendation(**kw)


@pytest.mark.parametrize("bad_rank", [0, 6, -1, 10])
def test_v1_covered_rank_out_of_range(bad_rank: int) -> None:
    """V1: is_covered=True with rank outside [1,5] raises ValidationError."""
    kw = _covered_kwargs()
    kw["rank"] = bad_rank
    with pytest.raises(ValidationError, match="V1"):
        ChangeRecommendation(**kw)


# ---------------------------------------------------------------------------
# V2: is_covered=False ⇒ rank is None
# ---------------------------------------------------------------------------

def test_v2_uncovered_rank_not_none() -> None:
    """V2: is_covered=False with a non-None rank raises ValidationError."""
    kw = _uncovered_kwargs()
    kw["rank"] = 3
    with pytest.raises(ValidationError, match="V2"):
        ChangeRecommendation(**kw)


# ---------------------------------------------------------------------------
# Extra-field rejection + frozen
# ---------------------------------------------------------------------------

def test_extra_field_rejected() -> None:
    """extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        ChangeRecommendation(**_covered_kwargs(), unknown_field="bad")


def test_frozen_prevents_mutation() -> None:
    """frozen=True prevents in-place attribute mutation."""
    rec = ChangeRecommendation(**_covered_kwargs())
    with pytest.raises(Exception):
        rec.rank = 2  # type: ignore[misc]
