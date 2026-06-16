"""T027 — Markdown → PDF renderer for retro-mester reports.

Entry point: ``write_report_pdf(md_text, pdf_path, when)``.

Determinism:
- ``SOURCE_DATE_EPOCH`` is set from ``when`` for the duration of the
  reportlab build, pinning CreationDate / ModDate so two runs with the
  same ``when`` produce byte-identical PDFs.
- Producer / Creator / Title are fixed strings.

NanumGothic resolution: uses ``retro_mester.output.fonts`` (self-contained
copy of immersio's font resolution, no cross-module runtime coupling).
"""

from __future__ import annotations

import contextlib
import datetime
import os
from collections.abc import Generator
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate

from retro_mester.output.fonts import register_for_reportlab, resolve_korean_font_paths
from retro_mester.output.md_parser import parse_markdown_to_flowables

_PRODUCER = "paideia/retro-mester/0.1.0"
_DOC_TITLE = "학기회고보고서"


@contextlib.contextmanager
def _pin_source_date_epoch(epoch: int) -> Generator[None, None, None]:
    """Context manager that pins ``SOURCE_DATE_EPOCH`` for the wrapped block.

    reportlab's ``TimeStamp`` honours this env-var so the resulting
    PDF's CreationDate / ModDate reflect ``epoch`` rather than the
    host clock.

    Args:
        epoch: Unix timestamp to pin.
    """
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(int(epoch))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous


def _to_epoch(when: datetime.datetime) -> int:
    """Convert ``when`` to a Unix epoch integer.

    Args:
        when: A datetime object (naive = UTC, aware = converted to UTC).

    Returns:
        Integer Unix timestamp.
    """
    if when.tzinfo is None:
        aware = when.replace(tzinfo=datetime.UTC)
    else:
        aware = when.astimezone(datetime.UTC)
    return int(aware.timestamp())


def write_report_pdf(
    md_text: str,
    pdf_path: Path,
    when: datetime.datetime,
) -> None:
    """Render ``md_text`` to a deterministic PDF at ``pdf_path``.

    Never calls ``datetime.now()`` internally; ``when`` is the single
    source of truth for all metadata timestamps.

    Args:
        md_text: Markdown report string (from ``build_report_md``).
        pdf_path: Destination ``.pdf`` path.
        when: Timestamp pinned onto CreationDate / ModDate /
            SOURCE_DATE_EPOCH for byte-identical reproducibility.

    Raises:
        ValueError: When ``md_text`` is empty.
        FileNotFoundError: When ``pdf_path.parent`` does not exist.
    """
    if not isinstance(md_text, str) or not md_text.strip():
        raise ValueError("write_report_pdf: md_text must be a non-empty string")
    pdf_path = Path(pdf_path)
    if not pdf_path.parent.is_dir():
        raise FileNotFoundError(f"write_report_pdf: parent directory missing: {pdf_path.parent}")

    regular_path, bold_path = resolve_korean_font_paths()
    regular_name, bold_name = register_for_reportlab(regular_path, bold_path)

    styles = getSampleStyleSheet()
    for style_name in ("BodyText", "Heading1", "Heading2", "Heading3"):
        styles[style_name].fontName = regular_name
    styles["Heading1"].fontName = bold_name
    styles["Heading2"].fontName = bold_name

    flowables = parse_markdown_to_flowables(md_text, image_base_dir=pdf_path.parent)

    epoch = _to_epoch(when)

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        title=_DOC_TITLE,
        author=_PRODUCER,
        creator=_PRODUCER,
        producer=_PRODUCER,
    )

    def _pin_metadata(canvas: object, _doc: object) -> None:  # type: ignore[no-untyped-def]
        canvas.setProducer(_PRODUCER)
        canvas.setCreator(_PRODUCER)
        canvas.setTitle(_DOC_TITLE)
        canvas.setAuthor(_PRODUCER)

    with _pin_source_date_epoch(epoch):
        doc.build(flowables, onFirstPage=_pin_metadata, onLaterPages=_pin_metadata)


__all__ = ["write_report_pdf"]
