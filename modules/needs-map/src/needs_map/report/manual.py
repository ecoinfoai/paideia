"""Operator manual PDF renderer [T047, FR-023 + FR-024].

Reads ``shared/paideia_shared/src/paideia_shared/assets/manual_text.ko.yaml``
via the ``ManualTextAsset`` schema (T016) and walks its sections to build
a reportlab Platypus story (10–15 page A4 portrait, NanumGothic, ≥3
embedded figures from ``manual_figures/``).

Determinism (FR-035): NanumGothic fonts registered via
``needs_map.fonts.register_for_reportlab``, Producer + Creator pinned, no
LLM in the rendering path. Two consecutive renders against the same
asset YAML + figures + cohort context produce byte-equal PDFs.

Spec: 003-needs-map-v0-1-1/tasks.md T047; FR-023; FR-024; FR-035;
data-model.md "매뉴얼 자산 데이터 모델".
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml
from paideia_shared.assets.manual_text import ManualTextAsset
from reportlab.lib import pagesizes
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..fonts import register_for_reportlab, resolve_korean_font_paths

_PRODUCER = "paideia/needs-map/0.1.1"
_CREATOR = "paideia/needs-map/0.1.1"

# manual_figures directory ships alongside the asset YAML.
_FIGURES_PACKAGE = "paideia_shared.assets.manual_figures"
_RADAR_FIGURE = "radar_example.png"
_DISTRIBUTION_FIGURE = "distribution_example.png"
_CLUSTER_FIGURE = "cluster_example.png"

# Section IDs that get a figure inserted at the end of their content.
_FIGURE_BY_SECTION_ID = {
    "outputs_reading": _DISTRIBUTION_FIGURE,
    "zscore_clustering": _CLUSTER_FIGURE,
    "operating_scenarios": _RADAR_FIGURE,
}


def _load_asset() -> ManualTextAsset:
    """Load + validate the v0.1.1 Korean manual asset YAML.

    Resolved via ``importlib.resources`` so the asset path stays consistent
    whether the wheel is installed or the source tree is used in editable
    mode.
    """
    package = "paideia_shared.assets"
    with resources.files(package).joinpath("manual_text.ko.yaml").open("rb") as f:
        data = yaml.safe_load(f.read().decode("utf-8"))
    return ManualTextAsset(**data)


def _figure_path(name: str) -> Path:
    """Locate one bundled figure on disk (importlib.resources files API)."""
    files = resources.files(_FIGURES_PACKAGE)
    return Path(str(files.joinpath(name)))


def render_manual_pdf(
    *,
    output_path: Path,
    semester: str,
    course_name_kr: str,
    cohort_n: int,
    created_at_utc: str,
) -> None:
    """Render the operator manual PDF at ``output_path``.

    Args:
        output_path: Filesystem destination for the PDF (gold tier).
        semester: Semester string used in the page header (e.g. ``2026-1``).
        course_name_kr: Korean course name shown in the cover header.
        cohort_n: Cohort size; surfaces in ``"전체 평균 n=<cohort_n>"``
          mentions if the renderer ever needs it (currently informational).
        created_at_utc: ISO8601 UTC timestamp; only used when manifest
          archeology surfaces the run date.
    """
    if not isinstance(output_path, Path):
        raise TypeError(
            f"render_manual_pdf: expected pathlib.Path, got {type(output_path).__name__}."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    regular_path, bold_path = resolve_korean_font_paths()
    regular_name, bold_name = register_for_reportlab(regular_path, bold_path)
    asset = _load_asset()

    style_body = ParagraphStyle(
        name="ManualBody",
        fontName=regular_name,
        fontSize=10,
        leading=14,
    )
    style_heading = ParagraphStyle(
        name="ManualHeading",
        fontName=bold_name,
        fontSize=14,
        leading=18,
        spaceBefore=10,
        spaceAfter=6,
    )
    style_axis_label = ParagraphStyle(
        name="ManualAxisLabel",
        fontName=bold_name,
        fontSize=10,
        leading=13,
    )
    style_axis_meaning = ParagraphStyle(
        name="ManualAxisMeaning",
        fontName=regular_name,
        fontSize=9,
        leading=12,
    )
    style_cover_title = ParagraphStyle(
        name="ManualCoverTitle",
        fontName=bold_name,
        fontSize=22,
        leading=28,
        spaceAfter=6,
    )
    style_cover_meta = ParagraphStyle(
        name="ManualCoverMeta",
        fontName=regular_name,
        fontSize=11,
        leading=16,
    )

    story: list = []

    # Cover (compact — counts as part of the 10-15 page budget)
    story.append(Paragraph("needs-map 운영자 매뉴얼", style_cover_title))
    story.append(
        Paragraph(
            f"{semester} · {course_name_kr} · 코호트 n={cohort_n}",
            style_cover_meta,
        )
    )
    story.append(
        Paragraph(
            f"본 매뉴얼은 매 needs-map 실행과 함께 자동 산출됩니다 (생성: {created_at_utc}).",
            style_cover_meta,
        )
    )
    story.append(Spacer(1, 6 * mm))

    for section in asset.sections:
        story.append(Paragraph(section.title, style_heading))
        for paragraph in section.body_paragraphs:
            story.append(Paragraph(paragraph, style_body))
            story.append(Spacer(1, 2 * mm))

        # 8-axis section: render axis_entries as a table.
        if section.axis_entries:
            rows: list[list[object]] = [
                [
                    Paragraph("축 키", style_axis_label),
                    Paragraph("한국어명", style_axis_label),
                    Paragraph("의미", style_axis_label),
                    Paragraph("운영 활용", style_axis_label),
                ]
            ]
            for entry in section.axis_entries:
                rows.append(
                    [
                        Paragraph(entry.key, style_axis_meaning),
                        Paragraph(entry.name_kr, style_axis_label),
                        Paragraph(entry.meaning, style_axis_meaning),
                        Paragraph(entry.operating_use, style_axis_meaning),
                    ]
                )
            table = Table(rows, colWidths=[28 * mm, 28 * mm, 60 * mm, 60 * mm])
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.25, (0.7, 0.7, 0.7)),
                        ("BACKGROUND", (0, 0), (-1, 0), (0.95, 0.95, 0.95)),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 4 * mm))

        if section.group_entries:
            rows = [
                [
                    Paragraph("그룹 키", style_axis_label),
                    Paragraph("한국어명", style_axis_label),
                    Paragraph("운영 활용", style_axis_label),
                ]
            ]
            for entry in section.group_entries:
                rows.append(
                    [
                        Paragraph(entry.key, style_axis_meaning),
                        Paragraph(entry.name_kr, style_axis_label),
                        Paragraph(entry.operating_use, style_axis_meaning),
                    ]
                )
            table = Table(rows, colWidths=[40 * mm, 40 * mm, 96 * mm])
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.25, (0.7, 0.7, 0.7)),
                        ("BACKGROUND", (0, 0), (-1, 0), (0.95, 0.95, 0.95)),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 4 * mm))

        figure_name = _FIGURE_BY_SECTION_ID.get(section.id)
        if figure_name is not None:
            story.append(Image(str(_figure_path(figure_name)), width=140 * mm, height=88 * mm))
            story.append(Spacer(1, 4 * mm))

        # Force a page break after each section so page count is predictable.
        story.append(PageBreak())

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=pagesizes.A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="needs-map 운영자 매뉴얼",
        author=_CREATOR,
        subject=f"{semester} {course_name_kr}",
        creator=_CREATOR,
        producer=_PRODUCER,
    )

    # Pin the PDF metadata to deterministic values so two runs match
    # byte-for-byte. SimpleDocTemplate honours ``producer`` / ``creator`` /
    # etc. above; CreationDate is set on the canvas via onFirstPage.
    def _on_first_page(canvas, _doc) -> None:  # noqa: ANN001
        canvas.setProducer(_PRODUCER)
        canvas.setCreator(_CREATOR)
        canvas.setTitle("needs-map 운영자 매뉴얼")
        canvas.setSubject(f"{semester} {course_name_kr}")
        # ISO8601 → reportlab D:YYYYMMDDHHmmSSZ
        pdf_date = "D:" + created_at_utc.replace("-", "").replace(":", "").rstrip("Z") + "Z"
        canvas._doc.info.creationDate = pdf_date  # type: ignore[attr-defined]
        canvas._doc.info.modDate = pdf_date  # type: ignore[attr-defined]

    doc.build(story, onFirstPage=_on_first_page, onLaterPages=_on_first_page)


__all__ = ["render_manual_pdf"]
