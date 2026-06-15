"""Contract tests for RetroManifest (M7, T011).

RED → GREEN: written before schema; ensure valid construction and
extra-field rejection fire correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paideia_shared.schemas import RetroManifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_kwargs() -> dict:
    return {
        "module_version": "0.1.0",
        "schema_version": "0.1.0",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "inputs": {
            "combined_silver": "data/silver/immersio/2026-1-anatomy/진단×시험결합.parquet",
            "config": "configs/retro/2026-1-anatomy.yaml",
        },
        "thresholds": {
            "gap_threshold": 0.6,
            "low_discrimination_threshold": 0.2,
            "cognitive_cliff_drop": 0.15,
        },
        "counts": {
            "unit_gaps": 12.0,
            "recommendations_covered": 5.0,
            "alignment_findings": 10.0,
        },
        "degrade": {
            "gap_engine": False,
            "recommendation_engine": False,
            "alignment_engine": "skipped: tested_items<5 for 2장",
        },
        "generated_at_utc": "2026-06-16T03:00:00Z",
    }


# ---------------------------------------------------------------------------
# Valid construction
# ---------------------------------------------------------------------------

def test_valid_construction() -> None:
    """A fully specified RetroManifest is accepted."""
    manifest = RetroManifest(**_valid_kwargs())
    assert manifest.module_version == "0.1.0"
    assert manifest.semester == "2026-1"
    assert manifest.counts["unit_gaps"] == 12.0


def test_degrade_bool_values() -> None:
    """degrade dict accepts both bool and str values."""
    kw = _valid_kwargs()
    kw["degrade"] = {"stage_a": True, "stage_b": False, "stage_c": "partial failure"}
    manifest = RetroManifest(**kw)
    assert manifest.degrade["stage_a"] is True
    assert manifest.degrade["stage_b"] is False
    assert manifest.degrade["stage_c"] == "partial failure"


def test_empty_dicts_accepted() -> None:
    """Empty inputs, thresholds, counts, degrade dicts are accepted."""
    kw = _valid_kwargs()
    kw["inputs"] = {}
    kw["thresholds"] = {}
    kw["counts"] = {}
    kw["degrade"] = {}
    manifest = RetroManifest(**kw)
    assert manifest.inputs == {}


# ---------------------------------------------------------------------------
# Extra-field rejection + frozen
# ---------------------------------------------------------------------------

def test_extra_field_rejected() -> None:
    """extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        RetroManifest(**_valid_kwargs(), unknown_field="bad")


def test_frozen_prevents_mutation() -> None:
    """frozen=True prevents in-place attribute mutation."""
    manifest = RetroManifest(**_valid_kwargs())
    with pytest.raises(Exception):
        manifest.module_version = "0.2.0"  # type: ignore[misc]
