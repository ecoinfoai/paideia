"""Contract tests for RetroManifest (M7, T011) and InputProvenance (T006).

RED → GREEN: written before schema; ensure valid construction and
extra-field rejection fire correctly.

T006 additions (v0.1.1):
- ``inputs`` is now ``dict[str, InputProvenance]`` (nested path+sha256 map).
- ``warnings`` defaults to ``[]`` when omitted.
- ``InputProvenance`` is exported from paideia_shared.schemas.
"""

from __future__ import annotations

import pytest
from paideia_shared.schemas import InputProvenance, RetroManifest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHA256_A = "a" * 64  # valid 64-char lowercase hex


def _valid_provenance() -> dict:
    """Return a valid InputProvenance dict."""
    return {"path": "data/silver/immersio/2026-1-anatomy/진단×시험결합.parquet", "sha256": _SHA256_A}


def _valid_kwargs() -> dict:
    return {
        "module_version": "0.1.1",
        "schema_version": "0.1.1",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "inputs": {
            "combined": _valid_provenance(),
            "config": {"path": "configs/retro/2026-1-anatomy.yaml", "sha256": "b" * 64},
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
    assert manifest.module_version == "0.1.1"
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


# ---------------------------------------------------------------------------
# T006: inputs is dict[str, InputProvenance] — nested path+sha256 mapping
# ---------------------------------------------------------------------------


def test_inputs_is_nested_provenance_mapping() -> None:
    """inputs values are InputProvenance objects (path + sha256), not bare strings."""
    manifest = RetroManifest(**_valid_kwargs())
    prov = manifest.inputs["combined"]
    assert isinstance(prov, InputProvenance)
    assert prov.path == "data/silver/immersio/2026-1-anatomy/진단×시험결합.parquet"
    assert prov.sha256 == _SHA256_A


def test_inputs_plain_string_rejected() -> None:
    """inputs values that are plain strings (old schema) are rejected."""
    kw = _valid_kwargs()
    kw["inputs"] = {"combined": "data/silver/immersio/2026-1-anatomy/진단×시험결합.parquet"}
    with pytest.raises(ValidationError):
        RetroManifest(**kw)


# ---------------------------------------------------------------------------
# T006: warnings defaults to []
# ---------------------------------------------------------------------------


def test_warnings_defaults_to_empty_list() -> None:
    """warnings field defaults to [] when not supplied."""
    manifest = RetroManifest(**_valid_kwargs())
    assert manifest.warnings == []


def test_warnings_accepts_list_of_strings() -> None:
    """warnings accepts a list of string messages."""
    kw = _valid_kwargs()
    kw["warnings"] = ["chapter name mismatch: '3장 세포' vs '3장 세포와 조직'"]
    manifest = RetroManifest(**kw)
    assert len(manifest.warnings) == 1
    assert "mismatch" in manifest.warnings[0]


# ---------------------------------------------------------------------------
# T006: InputProvenance contract
# ---------------------------------------------------------------------------


def test_input_provenance_valid() -> None:
    """InputProvenance accepts a valid path and 64-char lowercase hex sha256."""
    prov = InputProvenance(path="some/file.parquet", sha256="c" * 64)
    assert prov.sha256 == "c" * 64


def test_input_provenance_sha256_too_short_rejected() -> None:
    """InputProvenance rejects sha256 that is not 64 chars."""
    with pytest.raises(ValidationError):
        InputProvenance(path="some/file.parquet", sha256="abc123")


def test_input_provenance_sha256_uppercase_rejected() -> None:
    """InputProvenance rejects sha256 with uppercase hex digits."""
    with pytest.raises(ValidationError):
        InputProvenance(path="some/file.parquet", sha256="A" * 64)


def test_input_provenance_extra_field_rejected() -> None:
    """extra='forbid' on InputProvenance rejects unknown fields."""
    with pytest.raises(ValidationError):
        InputProvenance(path="f.parquet", sha256="d" * 64, extra="bad")


def test_input_provenance_frozen() -> None:
    """InputProvenance is frozen."""
    prov = InputProvenance(path="f.parquet", sha256="e" * 64)
    with pytest.raises(Exception):
        prov.path = "other.parquet"  # type: ignore[misc]
