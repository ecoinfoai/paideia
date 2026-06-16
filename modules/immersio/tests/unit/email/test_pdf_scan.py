"""Phase B PDF scan tests (T033)."""

from __future__ import annotations

from pathlib import Path

import pytest
from immersio.email.pdf_scan import (
    PDFScanError,
    parse_filename_pattern,
    scan_pdf_directory,
)
from reportlab.pdfgen import canvas


def _make_pdf(path: Path, text: str = "Sample PDF body") -> Path:
    """Create a minimal one-page PDF containing ``text`` on page 1."""
    c = canvas.Canvas(str(path))
    c.drawString(100, 750, text)
    c.showPage()
    c.save()
    return path


def test_parse_filename_pattern_valid() -> None:
    assert parse_filename_pattern("1234567890_홍길동.pdf") == (
        "1234567890",
        "홍길동",
    )


def test_parse_filename_pattern_violation_rejected() -> None:
    with pytest.raises(PDFScanError, match="FR-A04"):
        parse_filename_pattern("홍길동.pdf")  # no student_id prefix
    with pytest.raises(PDFScanError, match="FR-A04"):
        parse_filename_pattern("12345_홍길동.pdf")  # 5-digit not 10
    with pytest.raises(PDFScanError, match="FR-A04"):
        parse_filename_pattern("1234567890_홍길동.txt")  # wrong extension


def test_scan_normal_pdfs(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "이메일_발송용"
    pdf_dir.mkdir()
    _make_pdf(pdf_dir / "1234567890_홍길동.pdf", text="학번: 1234567890")
    _make_pdf(pdf_dir / "1234567891_김갑동.pdf", text="학번: 1234567891")
    bundles = scan_pdf_directory(pdf_dir)
    assert len(bundles) == 2
    assert [b.student_id for b in bundles] == ["1234567890", "1234567891"]
    assert all(len(b.pdf_sha256) == 64 for b in bundles)


def test_scan_filename_violation_aborts(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "이메일_발송용"
    pdf_dir.mkdir()
    _make_pdf(pdf_dir / "1234567890_홍길동.pdf")
    _make_pdf(pdf_dir / "no-pattern.pdf")
    with pytest.raises(PDFScanError, match="FR-A04"):
        scan_pdf_directory(pdf_dir)


def test_scan_duplicate_student_id_aborts(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "이메일_발송용"
    pdf_dir.mkdir()
    _make_pdf(pdf_dir / "1234567890_홍길동.pdf")
    _make_pdf(pdf_dir / "1234567890_가짜이름.pdf")
    with pytest.raises(PDFScanError, match="FR-A07"):
        scan_pdf_directory(pdf_dir)


def test_scan_directory_missing(tmp_path: Path) -> None:
    with pytest.raises(PDFScanError, match="not found"):
        scan_pdf_directory(tmp_path / "nonexistent")


def test_scan_sorted_by_student_id(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    _make_pdf(pdf_dir / "1234567002_zeta.pdf")
    _make_pdf(pdf_dir / "1234567001_alpha.pdf")
    _make_pdf(pdf_dir / "1234567003_beta.pdf")
    bundles = scan_pdf_directory(pdf_dir)
    assert [b.student_id for b in bundles] == [
        "1234567001",
        "1234567002",
        "1234567003",
    ]


def test_scan_body_contains_student_id_true(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    _make_pdf(pdf_dir / "1234567890_홍길동.pdf", text="학번 1234567890")
    [bundle] = scan_pdf_directory(pdf_dir)
    assert bundle.body_contains_student_id is True


def test_filename_path_traversal_rejected() -> None:
    """AV-S2 (adversary advisory): ``{이름}`` with traversal segment rejected."""
    with pytest.raises(PDFScanError, match="path-traversal"):
        parse_filename_pattern("1234567890_../escape.pdf")
    with pytest.raises(PDFScanError, match="path-traversal"):
        parse_filename_pattern("1234567890_evil/../name.pdf")
    with pytest.raises(PDFScanError, match="path-traversal"):
        parse_filename_pattern("1234567890_back\\slash.pdf")


def test_filename_nul_byte_rejected() -> None:
    """AV-S2: NUL byte in filename is rejected pre-regex."""
    with pytest.raises(PDFScanError, match="NUL byte"):
        parse_filename_pattern("1234567890_holder\x00.pdf")


def test_filename_control_byte_rejected() -> None:
    """AV-S2: ASCII control bytes (< 32) rejected pre-regex."""
    with pytest.raises(PDFScanError, match="control characters"):
        parse_filename_pattern("1234567890_holder\x01.pdf")
