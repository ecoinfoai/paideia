"""결합분석보고서.pdf writer — reuses Phase 1+2 MD parser + reportlab Platypus (T031, US1).

FR-002 / FR-004 / FR-023 + research §R6 #2/#7 + §R13 vector #3.

Phase 1+2 의 :func:`immersio.report.pdf_writer.render_quality_report_pdf`
는 title="시험품질보고서" 로 hardcode 됨. Phase 3 의 본 PDF 는
"결합분석보고서" 가 적합하므로 본 wrapper 가 build 단계를 직접 inherit
하면서 title 만 교체. 결정성 정책 (SOURCE_DATE_EPOCH + Producer/Creator
pin + UTF-16BE Korean title + parse_markdown_to_flowables) 모두 동일.

Public API:
- :func:`render_combined_analysis_pdf(md_text, output_path,
  created_at_utc, image_base_dir=None)` — md → 결합분석보고서.pdf
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate

from immersio import fonts as _fonts
from immersio.report.md_parser import parse_markdown_to_flowables
from immersio.report.pdf_writer import pin_source_date_epoch as _pin_source_date_epoch

_PRODUCER = "paideia/immersio/0.1.0"
_TITLE = "결합분석보고서"


def _to_epoch(iso_utc: str) -> int:
    """Parse ``YYYY-MM-DDThh:mm:ssZ`` → POSIX epoch (UTC)."""
    import datetime

    if not isinstance(iso_utc, str) or not iso_utc:
        raise ValueError(
            f"render_combined_analysis_pdf: created_at_utc must be a non-empty "
            f"string, got {iso_utc!r}"
        )
    s = iso_utc.replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(
            f"render_combined_analysis_pdf: created_at_utc is not valid "
            f"ISO-8601 (got {iso_utc!r})"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp())


def render_combined_analysis_pdf(
    *,
    md_text: str,
    output_path: Path,
    created_at_utc: str,
    image_base_dir: Path | None = None,
) -> None:
    """Render ``md_text`` to ``output_path`` as a deterministic Phase 3 PDF.

    Args:
        md_text: Output of :func:`combine.report_md.build_us1_report` (or the
            fuller phase-aware variant). The same string also lands as the
            ``.md`` companion (FR-004 — body text identity).
        output_path: Target ``.pdf`` path. Parent directory must exist
            (Phase 1+2 contract inherited — caller is responsible).
        created_at_utc: ISO8601 UTC timestamp pinned at the manifest;
            mapped onto Producer/CreationDate/ModDate via
            ``SOURCE_DATE_EPOCH``.
        image_base_dir: Optional base directory for relative
            ``![alt](path)`` resolution. Defaults to ``output_path.parent``.

    Raises:
        ValueError: When ``md_text`` is empty / whitespace-only or
            ``created_at_utc`` is not parseable.
        FileNotFoundError: When ``output_path.parent`` does not exist.
        immersio.fonts.KoreanFontUnavailableError: When NanumGothic is
            missing on the host (FR-023, exit 6 trigger).
    """
    if not isinstance(md_text, str) or not md_text.strip():
        raise ValueError(
            "render_combined_analysis_pdf: md_text must be a non-empty string"
        )
    output_path = Path(output_path)
    if not output_path.parent.is_dir():
        raise FileNotFoundError(
            f"render_combined_analysis_pdf: parent directory missing: "
            f"{output_path.parent}"
        )

    regular_path, bold_path = _fonts.resolve_korean_font_paths()
    regular_name, bold_name = _fonts.register_for_reportlab(
        regular_path, bold_path
    )

    # Patch the BodyText / Heading paragraph styles so md_parser's flowables
    # render Korean glyphs (Phase 1+2 inherit pattern).
    styles = getSampleStyleSheet()
    for style_name in ("BodyText", "Heading1", "Heading2", "Heading3"):
        styles[style_name].fontName = regular_name
    styles["Heading1"].fontName = bold_name
    styles["Heading2"].fontName = bold_name

    base = image_base_dir if image_base_dir is not None else output_path.parent
    flowables = parse_markdown_to_flowables(md_text, image_base_dir=base)

    epoch = _to_epoch(created_at_utc)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        title=_TITLE,
        author=_PRODUCER,
        creator=_PRODUCER,
        producer=_PRODUCER,
    )

    def _pin_metadata(canvas, _doc):
        canvas.setProducer(_PRODUCER)
        canvas.setCreator(_PRODUCER)
        canvas.setTitle(_TITLE)
        canvas.setAuthor(_PRODUCER)

    with _pin_source_date_epoch(epoch):
        doc.build(
            flowables,
            onFirstPage=_pin_metadata,
            onLaterPages=_pin_metadata,
        )


__all__ = ["render_combined_analysis_pdf"]
