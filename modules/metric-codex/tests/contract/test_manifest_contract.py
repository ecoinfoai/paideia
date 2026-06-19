"""Contract tests for MetricCodexManifest (spec 013 T011)."""

from __future__ import annotations

import pytest
from paideia_shared.schemas.metric_codex import AdvisorBundleSummary, MetricCodexManifest
from pydantic import ValidationError


def _valid_bundle():
    return AdvisorBundleSummary(
        total_students_with_codex=10,
        assigned_count=8,
        unassigned_sids=["2026194001", "2026194002"],
        advisor_count=3,
        per_advisor_counts={"advisor_A": 4, "advisor_B": 3, "advisor_C": 1},
    )


def _valid_manifest(**overrides):
    base = dict(
        semester="2026-1",
        course_slug="anatomy",
        input_hashes={"school_excel:성적출석.xlsx": "a" * 64},
        config_ids={"config.yaml": "b" * 64},
        generated_at="2026-06-01T00:00:00Z",
        llm_backend="none(template)",
        llm_model=None,
        cache_hit_rate=None,
        student_count=10,
        entry_count=120,
        bundle_summary=_valid_bundle(),
    )
    base.update(overrides)
    return base


class TestMetricCodexManifestValid:
    def test_valid_manifest_constructs(self):
        manifest = MetricCodexManifest(**_valid_manifest())
        assert manifest.semester == "2026-1"
        assert manifest.student_count == 10
        assert manifest.entry_count == 120

    def test_llm_backend_subscription(self):
        MetricCodexManifest(**_valid_manifest(llm_backend="subscription", llm_model="claude-sonnet-4-5"))

    def test_llm_backend_api(self):
        MetricCodexManifest(**_valid_manifest(llm_backend="api", llm_model="claude-opus-4-5"))

    def test_llm_backend_template(self):
        MetricCodexManifest(**_valid_manifest(llm_backend="none(template)", llm_model=None))

    def test_cache_hit_rate_zero(self):
        MetricCodexManifest(**_valid_manifest(llm_backend="api", llm_model="m", cache_hit_rate=0.0))

    def test_cache_hit_rate_one(self):
        MetricCodexManifest(**_valid_manifest(llm_backend="api", llm_model="m", cache_hit_rate=1.0))

    def test_embedded_bundle_summary_validates(self):
        manifest = MetricCodexManifest(**_valid_manifest())
        assert isinstance(manifest.bundle_summary, AdvisorBundleSummary)
        assert manifest.bundle_summary.total_students_with_codex == 10


class TestMetricCodexManifestInvalid:
    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            MetricCodexManifest(**_valid_manifest(unknown_field="x"))

    def test_invalid_llm_backend_rejected(self):
        with pytest.raises(ValidationError):
            MetricCodexManifest(**_valid_manifest(llm_backend="openai"))

    def test_invalid_semester_rejected(self):
        with pytest.raises(ValidationError):
            MetricCodexManifest(**_valid_manifest(semester="2026-3"))

    def test_invalid_course_slug_rejected(self):
        with pytest.raises(ValidationError):
            MetricCodexManifest(**_valid_manifest(course_slug="Anatomy"))

    def test_negative_student_count_rejected(self):
        with pytest.raises(ValidationError):
            MetricCodexManifest(**_valid_manifest(student_count=-1))

    def test_negative_entry_count_rejected(self):
        with pytest.raises(ValidationError):
            MetricCodexManifest(**_valid_manifest(entry_count=-1))

    def test_cache_hit_rate_above_one_rejected(self):
        with pytest.raises(ValidationError):
            MetricCodexManifest(**_valid_manifest(llm_backend="api", llm_model="m", cache_hit_rate=1.1))

    def test_cache_hit_rate_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            MetricCodexManifest(**_valid_manifest(llm_backend="api", llm_model="m", cache_hit_rate=-0.1))

    def test_embedded_bundle_invariant_violation_rejected(self):
        """Passing a bad bundle dict inline triggers validation."""
        bad_bundle = {
            "total_students_with_codex": 10,
            "assigned_count": 5,
            "unassigned_sids": [],  # 5 + 0 = 5 != 10
            "advisor_count": 1,
            "per_advisor_counts": {"advisor_A": 5},
        }
        with pytest.raises(ValidationError):
            MetricCodexManifest(**_valid_manifest(bundle_summary=bad_bundle))

    def test_missing_required_field_rejected(self):
        payload = _valid_manifest()
        del payload["semester"]
        with pytest.raises(ValidationError):
            MetricCodexManifest(**payload)

    def test_immutable(self):
        manifest = MetricCodexManifest(**_valid_manifest())
        with pytest.raises((ValidationError, TypeError)):
            manifest.student_count = 999  # type: ignore[misc]
