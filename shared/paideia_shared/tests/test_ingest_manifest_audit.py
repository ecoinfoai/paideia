"""Audit-trail tests for IngestManifest extension (spec 004 T018-followup, AV-A9).

Two new optional fields:
- ``exam_result_pattern_used: str | None``
- ``exclude_tokens_applied: list[str]``

Both default to ``None`` / ``[]`` so all 003-spec manifests stay valid.
"""

from __future__ import annotations

from datetime import UTC, datetime

from paideia_shared.schemas import (
    IngestInput,
    IngestManifest,
    IngestRowCount,
)


def _base_inputs() -> list[IngestInput]:
    """Build the five required IngestInput rows with placeholder sha256 values."""
    return [
        IngestInput(
            role=role,
            path=f"bronze/{role}.bin",
            sha256="0" * 64,
            encoding="utf-8" if role.endswith("_csv") else None,
        )
        for role in (
            "diagnostic_csv",
            "exam_omr_xls",
            "attendance_xlsx",
            "exam_yaml",
            "diagnostic_mapping_yaml",
        )
    ]


def _base_kwargs(**overrides) -> dict:
    base = dict(
        output_key="2026-1-anatomy",
        semester="2026-1",
        course_slug="anatomy",
        course_name_kr="해부생리학",
        paideia_shared_version="0.1.0",
        immersio_version="0.1.0",
        mapping_version=2,
        inputs=_base_inputs(),
        row_counts=IngestRowCount(
            student_master=184,
            diagnostic_response=8800,
            exam_result=8096,
            exam_item=44,
        ),
        created_at=datetime(2026, 4, 28, 14, 0, 0, tzinfo=UTC),
    )
    base.update(overrides)
    return base


def test_ingest_manifest_default_fields_backward_compat() -> None:
    """No exam_result_pattern_used / exclude_tokens_applied → defaults persist."""
    manifest = IngestManifest(**_base_kwargs())
    assert manifest.exam_result_pattern_used is None
    assert manifest.exclude_tokens_applied == []


def test_ingest_manifest_records_pattern_override() -> None:
    """When operator override active, manifest captures it for re-runnability."""
    manifest = IngestManifest(
        **_base_kwargs(
            exam_result_pattern_used="*A반*결과(OX).xls",
            exclude_tokens_applied=[],
        )
    )
    assert manifest.exam_result_pattern_used == "*A반*결과(OX).xls"
    assert manifest.exclude_tokens_applied == []


def test_ingest_manifest_records_default_exclude_tokens() -> None:
    """Default discovery → manifest lists the exact tokens that filtered files."""
    manifest = IngestManifest(
        **_base_kwargs(
            exam_result_pattern_used=None,
            exclude_tokens_applied=["(OX)", "(문항분석)", "결시"],
        )
    )
    assert manifest.exam_result_pattern_used is None
    assert manifest.exclude_tokens_applied == ["(OX)", "(문항분석)", "결시"]
