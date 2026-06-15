"""Contract tests for AlignmentFinding (M4, T008).

RED → GREEN: written before schema; ensure valid construction and
extra-field / Literal validation fire correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paideia_shared.schemas import AlignmentFinding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_kwargs() -> dict:
    return {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "chapter": "8장 호흡계통",
        "taught_weeks": 3,
        "tested_items": 10,
        "learned_rate": 0.61,
        "cognitive_profile": {"기억": 0.82, "이해": 0.65, "적용": 0.40},
        "flag": "정렬됨",
        "interest_gap": 0.12,
        "aversion_gap": -0.08,
        "note": "호흡계통은 교수-평가 정렬 양호.",
    }


# ---------------------------------------------------------------------------
# Valid construction
# ---------------------------------------------------------------------------

def test_valid_construction() -> None:
    """A fully specified AlignmentFinding is accepted."""
    finding = AlignmentFinding(**_valid_kwargs())
    assert finding.chapter == "8장 호흡계통"
    assert finding.flag == "정렬됨"
    assert finding.interest_gap == pytest.approx(0.12)


def test_valid_construction_optional_gaps_none() -> None:
    """interest_gap and aversion_gap may be None."""
    kw = _valid_kwargs()
    kw["interest_gap"] = None
    kw["aversion_gap"] = None
    finding = AlignmentFinding(**kw)
    assert finding.interest_gap is None
    assert finding.aversion_gap is None


def test_valid_construction_note_defaults_empty() -> None:
    """note has a default of empty string when omitted."""
    kw = _valid_kwargs()
    del kw["note"]
    finding = AlignmentFinding(**kw)
    assert finding.note == ""


# ---------------------------------------------------------------------------
# Literal validation
# ---------------------------------------------------------------------------

def test_invalid_flag_rejected() -> None:
    """A non-Literal flag value raises ValidationError."""
    kw = _valid_kwargs()
    kw["flag"] = "알수없음"  # not in AlignmentFlag
    with pytest.raises(ValidationError):
        AlignmentFinding(**kw)


# ---------------------------------------------------------------------------
# Non-negative field constraints
# ---------------------------------------------------------------------------

def test_negative_taught_weeks_rejected() -> None:
    """taught_weeks < 0 raises ValidationError."""
    kw = _valid_kwargs()
    kw["taught_weeks"] = -1
    with pytest.raises(ValidationError):
        AlignmentFinding(**kw)


def test_negative_tested_items_rejected() -> None:
    """tested_items < 0 raises ValidationError."""
    kw = _valid_kwargs()
    kw["tested_items"] = -1
    with pytest.raises(ValidationError):
        AlignmentFinding(**kw)


# ---------------------------------------------------------------------------
# Extra-field rejection + frozen
# ---------------------------------------------------------------------------

def test_extra_field_rejected() -> None:
    """extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        AlignmentFinding(**_valid_kwargs(), unknown_field="bad")


def test_frozen_prevents_mutation() -> None:
    """frozen=True prevents in-place attribute mutation."""
    finding = AlignmentFinding(**_valid_kwargs())
    with pytest.raises(Exception):
        finding.flag = "과소교수-과다평가"  # type: ignore[misc]
