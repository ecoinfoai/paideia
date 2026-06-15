"""T027 — Report PDF writer tests (RED phase).

Tests for ``retro_mester.output.report_pdf.write_report_pdf``.
- Produces a non-empty PDF file.
- Two writes with same ``when`` are byte-identical (SOURCE_DATE_EPOCH pinned).
"""

from __future__ import annotations

import datetime
from pathlib import Path

from retro_mester.output.report_pdf import write_report_pdf

_SAMPLE_MD = """\
# 회고 보고서

## (A) 변경 권고

| 순위 | 단원 | 집단 |
| --- | --- | --- |
| 1 | 1장 세포 | 학령기 |

못 덮은 빈틈 비율 = 33.3%
"""

_WHEN = datetime.datetime(2026, 6, 15, 9, 0, 0)


class TestWriteReportPdf:
    def test_creates_non_empty_pdf(self, tmp_path: Path) -> None:
        """write_report_pdf creates a non-empty .pdf file."""
        out = tmp_path / "report.pdf"
        write_report_pdf(_SAMPLE_MD, out, _WHEN)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_byte_identical_on_two_writes(self, tmp_path: Path) -> None:
        """Two writes with the same ``when`` produce byte-identical PDF files."""
        out1 = tmp_path / "report1.pdf"
        out2 = tmp_path / "report2.pdf"
        write_report_pdf(_SAMPLE_MD, out1, _WHEN)
        write_report_pdf(_SAMPLE_MD, out2, _WHEN)
        assert out1.read_bytes() == out2.read_bytes()

    def test_output_starts_with_pdf_header(self, tmp_path: Path) -> None:
        """Output file starts with the PDF magic bytes %PDF."""
        out = tmp_path / "report.pdf"
        write_report_pdf(_SAMPLE_MD, out, _WHEN)
        assert out.read_bytes()[:4] == b"%PDF"
