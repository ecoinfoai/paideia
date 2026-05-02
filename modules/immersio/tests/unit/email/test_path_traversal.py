"""Path-traversal + control-byte tests for CLI Path arguments (T101, FR-F01).

The email subparser accepts ``--bronze-csv``, ``--gold-pdf-dir``,
``--silver-master``, ``--silver-student-metrics`` as ``Path``. The
roster / pdf_scan / master_check / cohort_filter modules each emit
fail-fast errors via their own validators, so most traversal attacks
surface as ``RosterError`` / ``PDFScanError`` / ``CohortError`` (exit
code 3 or 4 per pipeline mapping). This contract test verifies the
errors emerge cleanly rather than the path being silently followed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from immersio.email.pdf_scan import PDFScanError, parse_filename_pattern


def test_pdf_filename_dotdot_rejected() -> None:
    """parse_filename_pattern rejects `..` segment in name_kr (AV-S2)."""
    with pytest.raises(PDFScanError, match="path-traversal"):
        parse_filename_pattern("1234567890_..\\evil.pdf")


def test_pdf_filename_forward_slash_rejected() -> None:
    with pytest.raises(PDFScanError, match="path-traversal"):
        parse_filename_pattern("1234567890_evil/sub.pdf")


def test_pdf_filename_backslash_rejected() -> None:
    with pytest.raises(PDFScanError, match="path-traversal"):
        parse_filename_pattern("1234567890_evil\\sub.pdf")


def test_pdf_filename_nul_byte_rejected() -> None:
    with pytest.raises(PDFScanError, match="NUL byte"):
        parse_filename_pattern("1234567890_holder\x00.pdf")


def test_pdf_filename_control_byte_rejected() -> None:
    with pytest.raises(PDFScanError, match="control characters"):
        parse_filename_pattern("1234567890_holder\x01.pdf")


def test_pdf_filename_normal_korean_accepted() -> None:
    sid, name = parse_filename_pattern("1234567890_홍길동.pdf")
    assert sid == "1234567890"
    assert name == "홍길동"


def test_pdf_filename_korean_with_space_accepted() -> None:
    sid, name = parse_filename_pattern("1234567890_홍 길동.pdf")
    assert sid == "1234567890"
    assert name == "홍 길동"
