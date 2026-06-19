"""T017 — Unit tests for metric_codex.output.manifest.

Tests (RED first, per TDD mandate):
- build_manifest: returns a valid MetricCodexManifest with all fields populated.
- write_manifest: produces sorted, deterministic JSON; two writes are byte-
  identical; the JSON round-trips back into a valid MetricCodexManifest; the
  file is written atomically (exists and valid after the call).
- write_manifest creates parent directories when they don't exist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from paideia_shared.schemas import AdvisorBundleSummary, MetricCodexManifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle_summary() -> AdvisorBundleSummary:
    """Return a minimal valid AdvisorBundleSummary for testing.

    CanonicalStudentId requires 10 numeric digits (pattern ``^\\d{10}$``).
    """
    return AdvisorBundleSummary(
        total_students_with_codex=3,
        assigned_count=2,
        unassigned_sids=["2026000003"],
        advisor_count=2,
        per_advisor_counts={"prof.kim": 1, "prof.lee": 1},
    )


def _build_test_manifest() -> MetricCodexManifest:
    """Return a minimal MetricCodexManifest suitable for round-trip tests."""
    from metric_codex.output.manifest import build_manifest

    return build_manifest(
        semester="2026-1",
        course_slug="anatomy",
        input_hashes={"grades.xlsx": "sha256:abc123", "attendance.xlsx": "sha256:def456"},
        config_ids={"성적출석_map.yaml": "sha256:ghi789"},
        generated_at="2026-06-19T00:00:00Z",
        llm_backend="none(template)",
        llm_model=None,
        cache_hit_rate=None,
        student_count=3,
        entry_count=9,
        bundle_summary=_make_bundle_summary(),
    )


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------


def test_build_manifest_returns_correct_type() -> None:
    """build_manifest returns a MetricCodexManifest instance."""
    manifest = _build_test_manifest()
    assert isinstance(manifest, MetricCodexManifest)


def test_build_manifest_fields_populated() -> None:
    """build_manifest populates all provided fields correctly."""
    manifest = _build_test_manifest()

    assert manifest.semester == "2026-1"
    assert manifest.course_slug == "anatomy"
    assert manifest.llm_backend == "none(template)"
    assert manifest.llm_model is None
    assert manifest.cache_hit_rate is None
    assert manifest.student_count == 3
    assert manifest.entry_count == 9
    assert isinstance(manifest.bundle_summary, AdvisorBundleSummary)


def test_build_manifest_with_api_backend() -> None:
    """build_manifest accepts api backend with model name and cache rate."""
    from metric_codex.output.manifest import build_manifest

    manifest = build_manifest(
        semester="2026-1",
        course_slug="anatomy",
        input_hashes={},
        config_ids={},
        generated_at="2026-06-19T00:00:00Z",
        llm_backend="api",
        llm_model="claude-3-5-sonnet-20241022",
        cache_hit_rate=0.75,
        student_count=0,
        entry_count=0,
        bundle_summary=AdvisorBundleSummary(
            total_students_with_codex=0,
            assigned_count=0,
            unassigned_sids=[],
            advisor_count=0,
            per_advisor_counts={},
        ),
    )
    assert manifest.llm_backend == "api"
    assert manifest.llm_model == "claude-3-5-sonnet-20241022"
    assert manifest.cache_hit_rate == 0.75


def test_build_manifest_invalid_backend_raises() -> None:
    """build_manifest rejects an unknown llm_backend literal."""
    import pydantic
    from metric_codex.output.manifest import build_manifest

    with pytest.raises(pydantic.ValidationError):
        build_manifest(
            semester="2026-1",
            course_slug="anatomy",
            input_hashes={},
            config_ids={},
            generated_at="2026-06-19T00:00:00Z",
            llm_backend="invalid-backend",  # type: ignore[arg-type]
            llm_model=None,
            cache_hit_rate=None,
            student_count=0,
            entry_count=0,
            bundle_summary=AdvisorBundleSummary(
                total_students_with_codex=0,
                assigned_count=0,
                unassigned_sids=[],
                advisor_count=0,
                per_advisor_counts={},
            ),
        )


# ---------------------------------------------------------------------------
# write_manifest — sorted, deterministic JSON
# ---------------------------------------------------------------------------


def test_write_manifest_produces_valid_json(tmp_path: Path) -> None:
    """write_manifest produces a file that parses as valid JSON."""
    from metric_codex.output.manifest import write_manifest

    manifest = _build_test_manifest()
    path = tmp_path / "manifest_metric-codex.json"
    write_manifest(path, manifest)

    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)


def test_write_manifest_sorted_keys(tmp_path: Path) -> None:
    """write_manifest produces JSON with top-level keys in sorted order."""
    from metric_codex.output.manifest import write_manifest

    manifest = _build_test_manifest()
    path = tmp_path / "manifest_metric-codex.json"
    write_manifest(path, manifest)

    parsed = json.loads(path.read_text(encoding="utf-8"))
    keys = list(parsed.keys())
    assert keys == sorted(keys), f"Top-level keys not sorted: {keys}"


def test_write_manifest_byte_identical_two_writes(tmp_path: Path) -> None:
    """Two write_manifest calls with the same manifest produce byte-identical files."""
    from metric_codex.output.manifest import write_manifest

    manifest = _build_test_manifest()
    path_a = tmp_path / "manifest_a.json"
    path_b = tmp_path / "manifest_b.json"

    write_manifest(path_a, manifest)
    write_manifest(path_b, manifest)

    assert path_a.read_bytes() == path_b.read_bytes()


def test_write_manifest_roundtrip(tmp_path: Path) -> None:
    """Manifest written and read back round-trips to an equal MetricCodexManifest."""
    from metric_codex.output.manifest import write_manifest

    manifest = _build_test_manifest()
    path = tmp_path / "manifest_metric-codex.json"
    write_manifest(path, manifest)

    raw = json.loads(path.read_text(encoding="utf-8"))
    restored = MetricCodexManifest.model_validate(raw)

    assert restored == manifest


def test_write_manifest_ensure_ascii_false(tmp_path: Path) -> None:
    """write_manifest writes Korean characters as-is (ensure_ascii=False)."""
    from metric_codex.output.manifest import build_manifest, write_manifest

    manifest = build_manifest(
        semester="2026-1",
        course_slug="anatomy",
        input_hashes={"성적.xlsx": "sha256:abc"},
        config_ids={},
        generated_at="2026-06-19T00:00:00Z",
        llm_backend="none(template)",
        llm_model=None,
        cache_hit_rate=None,
        student_count=0,
        entry_count=0,
        bundle_summary=AdvisorBundleSummary(
            total_students_with_codex=0,
            assigned_count=0,
            unassigned_sids=[],
            advisor_count=0,
            per_advisor_counts={},
        ),
    )
    path = tmp_path / "manifest_metric-codex.json"
    write_manifest(path, manifest)

    content = path.read_text(encoding="utf-8")
    assert "성적.xlsx" in content, "Korean key must appear as-is (ensure_ascii=False)"
    assert "\\u" not in content


def test_write_manifest_file_exists_after_write(tmp_path: Path) -> None:
    """write_manifest leaves the target file in place after a successful write."""
    from metric_codex.output.manifest import write_manifest

    manifest = _build_test_manifest()
    path = tmp_path / "manifest_metric-codex.json"
    write_manifest(path, manifest)

    assert path.exists()
    assert path.stat().st_size > 0


def test_write_manifest_creates_parent_dirs(tmp_path: Path) -> None:
    """write_manifest creates missing parent directories."""
    from metric_codex.output.manifest import write_manifest

    manifest = _build_test_manifest()
    nested = tmp_path / "deep" / "nested" / "manifest_metric-codex.json"
    write_manifest(nested, manifest)

    assert nested.exists()


def test_write_manifest_trailing_newline(tmp_path: Path) -> None:
    """write_manifest output ends with exactly one newline."""
    from metric_codex.output.manifest import write_manifest

    manifest = _build_test_manifest()
    path = tmp_path / "manifest_metric-codex.json"
    write_manifest(path, manifest)

    content = path.read_text(encoding="utf-8")
    assert content.endswith("\n")
    assert not content.endswith("\n\n")
