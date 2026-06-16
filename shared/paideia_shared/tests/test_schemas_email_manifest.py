"""Contract tests for EmailManifest (T012).

Validates SHA256 fields are hex64 and that no secret values land in the
serialised payload (data-model.md §1.6 secrets policy).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from paideia_shared.schemas import (
    DispatchMode,
    EmailManifest,
    EmailManifestCounts,
    EmailManifestInputs,
    EmailManifestOutputs,
)
from pydantic import ValidationError


def _valid_inputs() -> EmailManifestInputs:
    return EmailManifestInputs(
        bronze_csv_path="/abs/path/csv",
        bronze_csv_sha256="a" * 64,
        gold_pdf_dir_path="/abs/pdfdir",
        gold_pdf_count=184,
        silver_master_path="/abs/master.parquet",
        silver_master_sha256="b" * 64,
    )


def _valid_outputs() -> EmailManifestOutputs:
    return EmailManifestOutputs(
        silver_mapping_path="/abs/mapping.parquet",
        silver_mapping_rows=184,
        dispatch_log_path="/abs/log.csv",
        report_md_path="/abs/report.md",
    )


def _valid_counts() -> EmailManifestCounts:
    return EmailManifestCounts(
        success=100,
        skipped=10,
        failed=0,
        temporary_failure=0,
        dry_run=0,
        test_dummy=0,
    )


def _valid_manifest_kwargs() -> dict:
    return dict(
        semester="2026-1",
        course_slug="anatomy",
        course_name_kr="인체구조와기능",
        exam_name="중간고사",
        sent_date_kst=date(2026, 5, 1),
        mode=DispatchMode.PRODUCTION,
        profile_name="alpha-prof",
        profile_kind="operator",
        profile_secrets_ref_env_var_name="PAIDEIA_GCP_SA_JSON_PATH_ALPHA",
        inputs=_valid_inputs(),
        outputs=_valid_outputs(),
        counts=_valid_counts(),
        tool_version="0.1.0",
        started_at_kst=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        completed_at_kst=datetime(2026, 5, 1, 12, 5, 0, tzinfo=UTC),
    )


def test_valid_manifest_construction() -> None:
    m = EmailManifest(**_valid_manifest_kwargs())
    assert m.manifest_version == "1.0.0"
    assert m.ruleset_version == "immersio-email-v0.1.0"


def test_invalid_sha256_rejected() -> None:
    with pytest.raises(ValidationError):
        EmailManifestInputs(
            bronze_csv_path="/abs",
            bronze_csv_sha256="not-hex64",
            gold_pdf_dir_path="/abs",
            gold_pdf_count=1,
            silver_master_path="/abs",
            silver_master_sha256="b" * 64,
        )


def test_invalid_semester_rejected() -> None:
    kwargs = _valid_manifest_kwargs()
    kwargs["semester"] = "26-1"
    with pytest.raises(ValidationError):
        EmailManifest(**kwargs)


def test_no_private_key_in_serialised_payload() -> None:
    """Manifest JSON dump must not contain any secret-like field name."""
    m = EmailManifest(**_valid_manifest_kwargs())
    payload = json.dumps(m.model_dump(mode="json"))
    assert "private_key" not in payload
    assert "client_email" not in payload
    assert "BEGIN PRIVATE KEY" not in payload
    assert "iam.gserviceaccount.com" not in payload


def test_negative_counts_rejected() -> None:
    with pytest.raises(ValidationError):
        EmailManifestCounts(
            success=-1,
            skipped=0,
            failed=0,
            temporary_failure=0,
            dry_run=0,
            test_dummy=0,
        )


def test_extra_field_rejected() -> None:
    kwargs = _valid_manifest_kwargs()
    kwargs["leak"] = "anything"
    with pytest.raises(ValidationError):
        EmailManifest(**kwargs)
