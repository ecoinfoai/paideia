"""T032 — RED tests for `report/pdf_writer.py::render_quality_report_pdf` (R-05).

Two consecutive renders of the same Markdown source produce byte-
identical PDFs. ``Producer`` / ``Creator`` / ``CreationDate`` /
``ModDate`` must all be derived from the operator-supplied
``created_at_utc`` so the PDF can be sha256-pinned in the manifest.

Korean font resolution is bypassed via the same DejaVu monkeypatch the
figures test uses — determinism is the property under test, not font
resolution.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from immersio import fonts as _fonts
from immersio.report.pdf_writer import render_quality_report_pdf


@pytest.fixture(autouse=True)
def _resolve_font(monkeypatch: pytest.MonkeyPatch) -> None:
    from matplotlib import font_manager

    deja_vu_path = Path(font_manager.findfont("DejaVu Sans", fallback_to_default=True))
    monkeypatch.setattr(_fonts, "resolve_korean_font_paths", lambda: (deja_vu_path, deja_vu_path))


_MD_TEXT = """# 시험품질보고서 — 인체구조와기능 (2026-1)

발행: 2026-04-29T00:00:00Z

## (1) 전체 분포

응시자 184명 (결시 19명, 무응답 응답 12건).
전체 평균은 **125.35점** (SD 39.55), 중앙값 127.50점.

## (2) 메타데이터별 통계

### 분반

그룹간 차이 검정: **ANOVA** (p=0.012) — 유의함.

| 그룹 | n | 평균 | SD |
| --- | --- | --- | --- |
| A | 46 | 128.50 | 38.00 |
| B | 46 | 120.00 | 40.00 |

## (3) 변별력 요약

전체 44문항 중 변별력 < 0 (역변별) 문항 **1개**.
역변별 의심 문항: 12.

## (9) 권고사항

- 역변별 의심 문항 1개 — 출제 의도·정답 키 재검토 필수.
"""


def test_pdf_renders(tmp_path: Path) -> None:
    out = tmp_path / "report.pdf"
    render_quality_report_pdf(
        md_text=_MD_TEXT,
        output_path=out,
        created_at_utc="2026-04-29T00:00:00Z",
    )
    assert out.is_file()
    assert out.read_bytes()[:5] == b"%PDF-"


def test_pdf_two_calls_byte_identical(tmp_path: Path) -> None:
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    render_quality_report_pdf(
        md_text=_MD_TEXT,
        output_path=a,
        created_at_utc="2026-04-29T00:00:00Z",
    )
    render_quality_report_pdf(
        md_text=_MD_TEXT,
        output_path=b,
        created_at_utc="2026-04-29T00:00:00Z",
    )
    sha_a = hashlib.sha256(a.read_bytes()).hexdigest()
    sha_b = hashlib.sha256(b.read_bytes()).hexdigest()
    assert sha_a == sha_b, "PDF bytes diverge across two identical writes"


def test_pdf_producer_and_creator_pinned(tmp_path: Path) -> None:
    out = tmp_path / "report.pdf"
    render_quality_report_pdf(
        md_text=_MD_TEXT,
        output_path=out,
        created_at_utc="2026-04-29T00:00:00Z",
    )
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(str(out))
    info = reader.metadata
    assert "paideia" in str(info.producer or info.get("/Producer", ""))
    creation = info.creation_date or info.get("/CreationDate", "")
    creation_str = str(creation)
    assert "20260429" in creation_str or "2026-04-29" in creation_str, (
        f"CreationDate not pinned: {creation!r}"
    )


def test_pdf_rejects_empty_md() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "x.pdf"
        with pytest.raises(ValueError):
            render_quality_report_pdf(
                md_text="",
                output_path=out,
                created_at_utc="2026-04-29T00:00:00Z",
            )
