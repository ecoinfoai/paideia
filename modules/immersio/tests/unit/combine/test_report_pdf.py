"""TDD tests for ``combine.report_pdf`` (T031, US1).

Verifies the PDF writer:
- byte-identical re-runs (research §R13 vector #3 — SOURCE_DATE_EPOCH)
- PDF magic header ``%PDF-``
- title metadata "결합분석보고서" (NOT Phase 1+2's "시험품질보고서")
- empty md_text rejected
- relative image references resolve via ``image_base_dir``
"""

from __future__ import annotations

from pathlib import Path

import pytest
from immersio.combine.report_pdf import render_combined_analysis_pdf

_VALID_MD = """# 진단 × 시험 결합 분석 보고서

## 1. 분석 개요

본 보고서는 결합 분석 결과 요약.

## 2. 상관 매트릭스

표 1: 8 axes × N metrics

| axis | total_score |
|---|---|
| motivation | r=+0.32 |
"""


def test_writes_pdf_file(tmp_path: Path) -> None:
    out = tmp_path / "report.pdf"
    render_combined_analysis_pdf(
        md_text=_VALID_MD,
        output_path=out,
        created_at_utc="2026-04-30T00:00:00Z",
    )
    assert out.exists()
    assert out.stat().st_size > 0


def test_pdf_magic_header(tmp_path: Path) -> None:
    out = tmp_path / "report.pdf"
    render_combined_analysis_pdf(
        md_text=_VALID_MD,
        output_path=out,
        created_at_utc="2026-04-30T00:00:00Z",
    )
    assert out.read_bytes()[:5] == b"%PDF-"


def test_byte_identical_re_run(tmp_path: Path) -> None:
    """research §R13 vector #3 — SOURCE_DATE_EPOCH ctx pin → CreationDate/ModDate stable."""
    out1 = tmp_path / "r1.pdf"
    out2 = tmp_path / "r2.pdf"
    render_combined_analysis_pdf(
        md_text=_VALID_MD,
        output_path=out1,
        created_at_utc="2026-04-30T00:00:00Z",
    )
    render_combined_analysis_pdf(
        md_text=_VALID_MD,
        output_path=out2,
        created_at_utc="2026-04-30T00:00:00Z",
    )
    assert out1.read_bytes() == out2.read_bytes()


def test_title_metadata_combined_analysis(tmp_path: Path) -> None:
    """Title is "결합분석보고서" (NOT Phase 1+2's "시험품질보고서").

    Verified via pypdf which decodes the /Title metadata regardless of
    whether reportlab encoded it as PDFDocEncoding or UTF-16BE.
    """
    pypdf = pytest.importorskip("pypdf")
    out = tmp_path / "report.pdf"
    render_combined_analysis_pdf(
        md_text=_VALID_MD,
        output_path=out,
        created_at_utc="2026-04-30T00:00:00Z",
    )
    reader = pypdf.PdfReader(str(out))
    info = reader.metadata or {}
    title = str(info.get("/Title", ""))
    assert "결합분석" in title, f"PDF /Title does not contain '결합분석' (got {title!r})"
    assert "시험품질" not in title, (
        f"PDF /Title leaks Phase 1+2 'phase 1+2 시험품질' marker (got {title!r})"
    )


def test_empty_md_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="md_text"):
        render_combined_analysis_pdf(
            md_text="",
            output_path=tmp_path / "x.pdf",
            created_at_utc="2026-04-30T00:00:00Z",
        )


def test_whitespace_only_md_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="md_text"):
        render_combined_analysis_pdf(
            md_text="   \n  ",
            output_path=tmp_path / "x.pdf",
            created_at_utc="2026-04-30T00:00:00Z",
        )


def test_invalid_iso_timestamp_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        render_combined_analysis_pdf(
            md_text=_VALID_MD,
            output_path=tmp_path / "x.pdf",
            created_at_utc="not-a-timestamp",
        )


def test_image_base_dir_resolves_relative_path(tmp_path: Path) -> None:
    """Relative ![alt](figs/x.png) references resolve via image_base_dir.

    Uses matplotlib to materialize a real PNG so the resolver path is
    exercised end-to-end (Phase 1+2 inherit pattern).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figs = tmp_path / "figs"
    figs.mkdir()
    fig, ax = plt.subplots(figsize=(2.0, 1.0))
    ax.plot([0, 1], [0, 1])
    fig.savefig(figs / "x.png", format="png", dpi=72)
    plt.close(fig)

    md = _VALID_MD + "\n![테스트 이미지](figs/x.png)\n"
    out = tmp_path / "report.pdf"
    render_combined_analysis_pdf(
        md_text=md,
        output_path=out,
        created_at_utc="2026-04-30T00:00:00Z",
        image_base_dir=tmp_path,
    )
    assert out.exists()


def test_creates_parent_directory_via_caller(tmp_path: Path) -> None:
    """Caller is responsible for parent dir creation. Phase 1+2 raises
    FileNotFoundError when missing — we inherit that contract."""
    out = tmp_path / "deep" / "nest" / "report.pdf"
    with pytest.raises(FileNotFoundError):
        render_combined_analysis_pdf(
            md_text=_VALID_MD,
            output_path=out,
            created_at_utc="2026-04-30T00:00:00Z",
        )
