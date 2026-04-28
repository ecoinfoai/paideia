"""Operator manual PDF tests [T044, FR-023 + FR-024].

Per spec L97-101 + FR-023/FR-024:
- Manual PDF page count between 10 and 15 (A4 portrait).
- Body text contains every section title from FR-023.
- At least 3 image objects embedded (radar / distribution / cluster examples).
- Producer/CreationDate metadata are deterministic (same value across two runs).
- Two consecutive renders produce byte-identical bytes (FR-035).
- Altering only ``manual_text.ko.yaml`` (not code) changes the PDF
  (positive control — caller-driven content path actually works).

The test loads the bundled ``manual_text.ko.yaml`` asset (T045) and the
three ``manual_figures/*.png`` assets (T046) without any mock — this
exercises the real reportlab Platypus story.

Spec: 003-needs-map-v0-1-1/tasks.md T044; FR-023; FR-024; FR-035.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_FR023_SECTION_TITLES = (
    "모듈 소개",
    "8 정량 축 해석 가이드",
    "3 보조 카테고리 그룹 활용",
    "분석 phase A-F 개요",
    "산출물 읽는 법",
    "z-score와 군집 해석",
    "자유서술 결과 해석",
    "한계와 PII 정책",
    "운영 시나리오",
    "재실행과 archival 정책",
)


def _render(output_path: Path, **overrides: object) -> bytes:
    """Render the manual via the v0.1.1 ``render_manual_pdf`` helper."""
    from needs_map.report.manual import render_manual_pdf

    kwargs: dict[str, object] = {
        "output_path": output_path,
        "semester": "2026-1",
        "course_name_kr": "인체구조와기능",
        "cohort_n": 194,
        "created_at_utc": "2026-04-28T00:00:00Z",
    }
    kwargs.update(overrides)
    render_manual_pdf(**kwargs)  # type: ignore[arg-type]
    return output_path.read_bytes()


def test_manual_pdf_page_count_between_10_and_15(tmp_path: Path) -> None:
    """FR-024: A4 portrait, 10–15 pages."""
    from pypdf import PdfReader

    out = tmp_path / "manual.pdf"
    _render(out)
    reader = PdfReader(str(out))
    n_pages = len(reader.pages)
    assert 10 <= n_pages <= 15, f"expected 10-15 pages, got {n_pages}"


def test_manual_pdf_extracted_text_contains_all_section_titles(
    tmp_path: Path,
) -> None:
    """FR-023: every required section title appears in the rendered text."""
    from pypdf import PdfReader

    out = tmp_path / "manual.pdf"
    _render(out)
    reader = PdfReader(str(out))
    text = "".join(page.extract_text() or "" for page in reader.pages)
    missing = [title for title in _FR023_SECTION_TITLES if title not in text]
    assert not missing, f"missing FR-023 section titles in PDF: {missing}"


def test_manual_pdf_embeds_at_least_three_images(tmp_path: Path) -> None:
    """FR-024: ``≥ 3 illustrative figures`` (radar / distribution / cluster)."""
    from pypdf import PdfReader

    out = tmp_path / "manual.pdf"
    _render(out)
    reader = PdfReader(str(out))

    image_count = 0
    for page in reader.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        # ``XObject`` may be missing — guard via dict access.
        try:
            xobjects = resources["/XObject"]  # type: ignore[index]
        except (KeyError, TypeError):
            continue
        for obj_name in xobjects:  # type: ignore[union-attr]
            obj = xobjects[obj_name]  # type: ignore[index]
            if obj.get("/Subtype") == "/Image":
                image_count += 1
    assert image_count >= 3, (
        f"expected ≥3 embedded images, got {image_count}"
    )


def test_manual_pdf_byte_identical_two_renders(tmp_path: Path) -> None:
    """FR-035: two consecutive renders produce byte-equal bytes."""
    out_a = tmp_path / "a" / "manual.pdf"
    out_b = tmp_path / "b" / "manual.pdf"
    out_a.parent.mkdir()
    out_b.parent.mkdir()
    bytes_a = _render(out_a)
    bytes_b = _render(out_b)
    assert bytes_a == bytes_b, (
        "manual.pdf is non-deterministic — Producer/CreationDate or asset "
        "ordering drifted (FR-035 violation)"
    )


def test_manual_pdf_changes_when_asset_yaml_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control: editing manual_text.ko.yaml changes the PDF.

    Verifies the renderer actually reads the asset (not hardcoded). We
    monkeypatch the asset loader so the second render sees a modified
    section title; the byte streams must differ.
    """
    from needs_map.report import manual as manual_module

    out_a = tmp_path / "a" / "manual.pdf"
    out_b = tmp_path / "b" / "manual.pdf"
    out_a.parent.mkdir()
    out_b.parent.mkdir()

    bytes_a = _render(out_a)

    original_loader = manual_module._load_asset

    def _modified_loader() -> object:
        asset = original_loader()
        # Return a copy with one section title altered. Pydantic frozen
        # models force model_copy; freeze=False is fine via dict round trip.
        data = asset.model_dump()
        data["sections"][0]["title"] = "변경된 모듈 소개"  # forces text change
        # Re-validate to keep schema invariants
        from paideia_shared.assets.manual_text import ManualTextAsset

        return ManualTextAsset(**data)

    monkeypatch.setattr(manual_module, "_load_asset", _modified_loader)
    bytes_b = _render(out_b)

    assert bytes_a != bytes_b, (
        "manual.pdf identical despite asset YAML change — renderer is "
        "ignoring the asset (positive-control failed)"
    )
