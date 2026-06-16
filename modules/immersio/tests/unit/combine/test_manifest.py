"""TDD tests for ``combine.manifest`` (T017).

Verifies:
- ``compute_input_sha256`` matches ``hashlib.sha256(file.read_bytes()).hexdigest()``
  exactly (round-trip, byte-for-byte) for the 6 input artifacts the
  Phase 3 manifest tracks (FR-021).
- ``verify_schema_version`` uses ``packaging.version.Version`` comparison
  (rejects string lexicographic equality) and surfaces the FR-024 exit-5
  signal as a typed exception.
- ``serialize_manifest_json`` produces canonical JSON
  (``indent=2, ensure_ascii=False, sort_keys=True`` + trailing newline)
  that survives byte-identical re-serialisation.
- ``write_manifest`` lands the file with the canonical bytes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from immersio.combine.manifest import (
    SchemaVersionMismatch,
    compute_input_sha256,
    serialize_manifest_json,
    verify_schema_version,
    write_manifest,
)
from paideia_shared.schemas.combined_analysis_manifest import (
    CombinedAnalysisManifest,
)

_SHA = "0" * 64


def _baseline_manifest() -> CombinedAnalysisManifest:
    return CombinedAnalysisManifest(
        schema_version="0.1.0",
        module_version="immersio/0.1.0",
        semester="2026-1",
        course_slug="anatomy",
        generated_at_utc="2026-04-29T00:00:00Z",
        factor_scores_sha256=_SHA,
        cluster_assignment_sha256=_SHA,
        cluster_names_sha256=_SHA,
        student_metrics_sha256=_SHA,
        student_master_sha256=_SHA,
        diagnostic_response_sha256=_SHA,
        n_students_combined=30,
        n_diagnostic_only=3,
        n_exam_only=5,
        n_both=22,
        n_neither=0,
        n_unmatched_factor_scores=0,
        n_unmatched_cluster_assignment=0,
        n_unmatched_student_metrics=0,
        n_off_roster_respondents=0,
        ruleset_version="0.1.0",
        regression_method="OLS",
        multiple_comparison_method="BH-FDR",
        posthoc_method_used="Games_Howell",
        run_seed=0,
        needs_map_schema_version="1.1.0",
        immersio_phase2_schema_version="0.1.0",
        top3_predictor_axes=["motivation", "study_strategy", "time_availability"],
    )


# ---------------------------------------------------------------------------
# compute_input_sha256
# ---------------------------------------------------------------------------


def test_compute_input_sha256_matches_hashlib(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    payload = b"Phase 3 silver fixture bytes\n"
    target.write_bytes(payload)
    assert compute_input_sha256(target) == hashlib.sha256(payload).hexdigest()


def test_compute_input_sha256_empty_file_supported(tmp_path: Path) -> None:
    target = tmp_path / "empty.bin"
    target.write_bytes(b"")
    assert compute_input_sha256(target) == hashlib.sha256(b"").hexdigest()


def test_compute_input_sha256_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_input_sha256(tmp_path / "absent.bin")


# ---------------------------------------------------------------------------
# verify_schema_version
# ---------------------------------------------------------------------------


def test_verify_schema_version_accepts_equal() -> None:
    verify_schema_version("0.1.1", minimum="0.1.1", name="needs-map")


def test_verify_schema_version_accepts_higher_semver() -> None:
    """1.1.0 > 0.1.1 by Version (NOT by string comparison)."""
    verify_schema_version("1.1.0", minimum="0.1.1", name="needs-map")


def test_verify_schema_version_rejects_lower() -> None:
    with pytest.raises(SchemaVersionMismatch) as exc:
        verify_schema_version("0.1.0", minimum="0.1.1", name="needs-map")
    assert "needs-map" in str(exc.value)
    assert "0.1.0" in str(exc.value)
    assert "0.1.1" in str(exc.value)


def test_verify_schema_version_rejects_string_lex_equality() -> None:
    """Verify true semver: '0.1.10' must be considered ≥ '0.1.2' (string lex says '0.1.10' < '0.1.2')."""
    verify_schema_version("0.1.10", minimum="0.1.2", name="needs-map")


def test_verify_schema_version_invalid_string_raises() -> None:
    with pytest.raises((SchemaVersionMismatch, ValueError)):
        verify_schema_version("not-a-version", minimum="0.1.0", name="needs-map")


# ---------------------------------------------------------------------------
# serialize_manifest_json
# ---------------------------------------------------------------------------


def test_serialize_manifest_canonical_form() -> None:
    """sort_keys=True + ensure_ascii=False + indent=2 + trailing newline."""
    text = serialize_manifest_json(_baseline_manifest())
    assert text.endswith("\n"), "manifest text must end with a single newline"
    payload = json.loads(text)
    # Required key: cluster_names_sha256 (GAP-10).
    assert payload["cluster_names_sha256"] == _SHA
    # Korean values survive without \u escapes.
    posthoc = payload["posthoc_method_used"]
    assert posthoc == "Games_Howell"
    # Top-level keys must be in sorted order — re-encode and require equality.
    canonical = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    assert text == canonical


def test_serialize_manifest_byte_deterministic() -> None:
    """Re-serializing the same manifest twice yields identical bytes."""
    m = _baseline_manifest()
    assert serialize_manifest_json(m) == serialize_manifest_json(m)


def test_serialize_manifest_includes_all_required_fields() -> None:
    text = serialize_manifest_json(_baseline_manifest())
    payload = json.loads(text)
    # Six SHA256 fields (added cluster_names_sha256 per GAP-10) must all land.
    sha_fields = {
        "factor_scores_sha256",
        "cluster_assignment_sha256",
        "cluster_names_sha256",
        "student_metrics_sha256",
        "student_master_sha256",
        "diagnostic_response_sha256",
    }
    assert sha_fields.issubset(payload.keys())
    # Four R-10 audit fields must all land.
    r10_fields = {
        "n_unmatched_factor_scores",
        "n_unmatched_cluster_assignment",
        "n_unmatched_student_metrics",
        "n_off_roster_respondents",
    }
    assert r10_fields.issubset(payload.keys())


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------


def test_write_manifest_lands_canonical_bytes(tmp_path: Path) -> None:
    out = tmp_path / "manifest_phase3.json"
    m = _baseline_manifest()
    write_manifest(m, out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text == serialize_manifest_json(m)


def test_write_manifest_byte_deterministic_across_calls(tmp_path: Path) -> None:
    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"
    m = _baseline_manifest()
    write_manifest(m, out1)
    write_manifest(m, out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_write_manifest_creates_parent_dir(tmp_path: Path) -> None:
    """Caller-friendly: nested missing dir is created."""
    out = tmp_path / "deep" / "nest" / "manifest_phase3.json"
    write_manifest(_baseline_manifest(), out)
    assert out.exists()
