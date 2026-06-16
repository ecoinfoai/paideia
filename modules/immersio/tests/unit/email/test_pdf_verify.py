"""Phase D PDF body-verify tests (T035)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from immersio.email.pdf_verify import (
    verify_pdf_body_contains_student_id,
)
from paideia_shared.schemas import StudentPDFBundle


def _bundle(
    tmp_path: Path,
    *,
    sid: str = "1234567890",
    contains_id: bool = True,
    size_bytes: int | None = None,
) -> StudentPDFBundle:
    pdf = tmp_path / f"{sid}_홍길동.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF\n" * 5)
    return StudentPDFBundle(
        student_id=sid,
        name_kr="홍길동",
        pdf_path=pdf,
        pdf_filename=pdf.name,
        pdf_size_bytes=size_bytes if size_bytes is not None else pdf.stat().st_size,
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        body_first_page_text_normalized=f"학번{sid}" if contains_id else "",
        body_contains_student_id=contains_id,
    )


def test_normal_pdf_passes(tmp_path: Path) -> None:
    b = _bundle(tmp_path)
    result = verify_pdf_body_contains_student_id(b, attachment_max_bytes=10485760)
    assert result.ok is True
    assert result.error_kind == ""


def test_missing_student_id_skipped(tmp_path: Path) -> None:
    b = _bundle(tmp_path, contains_id=False)
    result = verify_pdf_body_contains_student_id(b, attachment_max_bytes=10485760)
    assert result.ok is False
    assert result.error_kind == "pdf_no_student_id"


def test_attachment_size_exceeded(tmp_path: Path) -> None:
    """101 MB > 100 MB max → failed + attachment_size_exceeded (FR-F02)."""
    b = _bundle(tmp_path, size_bytes=101 * 1024 * 1024)
    result = verify_pdf_body_contains_student_id(b, attachment_max_bytes=100 * 1024 * 1024)
    assert result.ok is False
    assert result.error_kind == "attachment_size_exceeded"


def test_attachment_size_exact_boundary_passes(tmp_path: Path) -> None:
    """Exactly 100 MB ≤ 100 MB max → pass (boundary inclusive)."""
    size = 100 * 1024 * 1024
    b = _bundle(tmp_path, size_bytes=size)
    result = verify_pdf_body_contains_student_id(b, attachment_max_bytes=size)
    assert result.ok is True


def test_invalid_max_bytes_rejected(tmp_path: Path) -> None:
    b = _bundle(tmp_path)
    with pytest.raises(ValueError):
        verify_pdf_body_contains_student_id(b, attachment_max_bytes=0)


def test_size_check_runs_before_body_check(tmp_path: Path) -> None:
    """Oversized PDF is rejected with size error even if body lacks ID."""
    b = _bundle(tmp_path, contains_id=False, size_bytes=200 * 1024 * 1024)
    result = verify_pdf_body_contains_student_id(b, attachment_max_bytes=100 * 1024 * 1024)
    assert result.error_kind == "attachment_size_exceeded"


def test_result_carries_original_bundle(tmp_path: Path) -> None:
    b = _bundle(tmp_path)
    result = verify_pdf_body_contains_student_id(b, attachment_max_bytes=10485760)
    assert result.bundle is b
