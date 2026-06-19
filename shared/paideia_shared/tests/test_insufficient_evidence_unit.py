"""Contract tests for InsufficientEvidenceUnit (T005, spec 012).

TDD: these tests are written before the schema implementation so they start RED
and turn GREEN once InsufficientEvidenceUnit is added to paideia_shared.

Invariant covered:
- V1: ``evidence_n`` must equal 0; any nonzero value raises ValidationError.
- Required fields: semester, course_slug, chapter, segment, evidence_n, reason.
- Model is frozen (mutations raise).
- extra='forbid' rejects unknown fields.
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import InsufficientEvidenceUnit
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
        "evidence_n": 0,
        "reason": "근거부족-자료없음",
    }


# ---------------------------------------------------------------------------
# Valid construction
# ---------------------------------------------------------------------------


def test_valid_construction() -> None:
    """A fully specified valid InsufficientEvidenceUnit is accepted."""
    unit = InsufficientEvidenceUnit(**_valid_kwargs())
    assert unit.semester == "2026-1"
    assert unit.course_slug == "anatomy"
    assert unit.chapter == "8장 호흡계통"
    assert unit.segment == "만학도"
    assert unit.evidence_n == 0
    assert unit.reason == "근거부족-자료없음"


def test_both_segment_values_accepted() -> None:
    """Both valid SegmentKey values are accepted."""
    kw = _valid_kwargs()
    kw["segment"] = "학령기"
    unit = InsufficientEvidenceUnit(**kw)
    assert unit.segment == "학령기"


# ---------------------------------------------------------------------------
# V1: evidence_n must be 0
# ---------------------------------------------------------------------------


def test_v1_evidence_n_nonzero_raises() -> None:
    """V1: evidence_n != 0 raises ValidationError."""
    kw = _valid_kwargs()
    kw["evidence_n"] = 1
    with pytest.raises(ValidationError, match="V1"):
        InsufficientEvidenceUnit(**kw)


def test_v1_evidence_n_negative_raises() -> None:
    """V1: negative evidence_n also raises ValidationError."""
    kw = _valid_kwargs()
    kw["evidence_n"] = -1
    with pytest.raises(ValidationError, match="V1"):
        InsufficientEvidenceUnit(**kw)


def test_v1_evidence_n_large_raises() -> None:
    """V1: evidence_n=15 (would be UnitGap territory) raises ValidationError."""
    kw = _valid_kwargs()
    kw["evidence_n"] = 15
    with pytest.raises(ValidationError, match="V1"):
        InsufficientEvidenceUnit(**kw)


# ---------------------------------------------------------------------------
# Field constraints
# ---------------------------------------------------------------------------


def test_empty_chapter_rejected() -> None:
    """chapter must be non-empty."""
    kw = _valid_kwargs()
    kw["chapter"] = ""
    with pytest.raises(ValidationError):
        InsufficientEvidenceUnit(**kw)


def test_invalid_segment_rejected() -> None:
    """segment must be one of the two SegmentKey literals."""
    kw = _valid_kwargs()
    kw["segment"] = "어려움"  # not a valid SegmentKey
    with pytest.raises(ValidationError):
        InsufficientEvidenceUnit(**kw)


def test_invalid_reason_rejected() -> None:
    """reason must be exactly the literal '근거부족-자료없음'."""
    kw = _valid_kwargs()
    kw["reason"] = "기타"
    with pytest.raises(ValidationError):
        InsufficientEvidenceUnit(**kw)


def test_invalid_semester_rejected() -> None:
    """semester must match the SemesterCode pattern."""
    kw = _valid_kwargs()
    kw["semester"] = "26-1"  # wrong format
    with pytest.raises(ValidationError):
        InsufficientEvidenceUnit(**kw)


def test_invalid_course_slug_rejected() -> None:
    """course_slug must match the CourseSlug pattern."""
    kw = _valid_kwargs()
    kw["course_slug"] = "Anatomy_Course"  # uppercase + underscore disallowed
    with pytest.raises(ValidationError):
        InsufficientEvidenceUnit(**kw)


# ---------------------------------------------------------------------------
# Extra-field rejection
# ---------------------------------------------------------------------------


def test_extra_field_rejected() -> None:
    """extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        InsufficientEvidenceUnit(**_valid_kwargs(), unknown_field="bad")


# ---------------------------------------------------------------------------
# Frozen
# ---------------------------------------------------------------------------


def test_frozen_prevents_mutation() -> None:
    """frozen=True prevents in-place attribute mutation."""
    unit = InsufficientEvidenceUnit(**_valid_kwargs())
    with pytest.raises(Exception):
        unit.chapter = "1장 서론"  # type: ignore[misc]
