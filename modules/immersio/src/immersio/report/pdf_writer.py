"""Quality report PDF writer (T041, FR-004, R-05).

reportlab Platypus + the immersio self-contained Markdown parser
(``report/md_parser.py``). The same Markdown source feeds both
``시험품질보고서.md`` and ``.pdf``, satisfying FR-004's "본문 텍스트 + 표 +
그림이 동일한 정보를 담도록" constraint.

Determinism (FR-023, SC-002):
* ``Producer`` / ``Creator`` pinned to ``paideia/immersio/0.1.0``.
* ``CreationDate`` / ``ModDate`` derived from the operator's
  ``created_at_utc`` argument (R-10 single source). reportlab reads the
  ``SOURCE_DATE_EPOCH`` env-var when available (reproducible-builds
  convention) — we set it to the matching epoch for the duration of the
  ``build()`` call so two runs produce byte-identical PDFs *and* the
  metadata reflects the manifest timestamp.
* The PDF ``/ID`` array is reportlab's md5(``signature``) digest of the
  document body — already deterministic for identical inputs.
"""

from __future__ import annotations

import contextlib
import datetime
import os
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate

from .. import fonts as _fonts
from .md_parser import parse_markdown_to_flowables

_PRODUCER = "paideia/immersio/0.1.0"


@contextlib.contextmanager
def _pin_source_date_epoch(epoch: int):
    """Set ``SOURCE_DATE_EPOCH`` for the wrapped block, restore on exit.

    reportlab's ``TimeStamp`` honours this env-var (see reportlab.pdfbase
    .pdfdoc.TimeStamp) so the resulting PDF's CreationDate / ModDate
    pin to ``epoch`` rather than the build-host clock.
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


def _to_pdf_date(iso_utc: str) -> str:
    """Format an ISO8601 UTC timestamp as ``D:YYYYMMDDHHmmSSZ`` (PDF spec)."""
    if not isinstance(iso_utc, str) or not iso_utc:
        raise ValueError(f"created_at_utc must be a non-empty string, got {iso_utc!r}")
    s = iso_utc.replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(
            f"created_at_utc is not a valid ISO8601 string: {iso_utc!r}"
        ) from exc
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return "D:" + dt.strftime("%Y%m%d%H%M%S") + "Z"


def _to_epoch(iso_utc: str) -> int:
    s = iso_utc.replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp())


def render_quality_report_pdf(
    *,
    md_text: str,
    output_path: Path,
    created_at_utc: str,
    image_base_dir: Path | None = None,
) -> None:
    """Render ``md_text`` to ``output_path`` as a deterministic PDF.

    Args:
        md_text: Output of ``render_quality_report_md`` — the same
            string is also written verbatim to the ``.md`` companion.
        output_path: Target ``.pdf`` path.
        created_at_utc: ISO8601 UTC timestamp pinned at the manifest;
            mapped onto Producer/CreationDate/ModDate.
        image_base_dir: Optional base directory used to resolve relative
            ``![alt](path)`` references inside ``md_text``. Defaults to
            ``output_path.parent`` so figures sitting next to the PDF
            (e.g. ``figs/fig1_*.png``) resolve naturally without the
            caller having to pre-rewrite the Markdown.

    Raises:
        ValueError: When ``md_text`` is empty.
        FileNotFoundError: When ``output_path.parent`` does not exist.
        immersio.fonts.KoreanFontUnavailableError: When NanumGothic is
            missing.
    """
    if not isinstance(md_text, str) or not md_text.strip():
        raise ValueError("render_quality_report_pdf: md_text must be a non-empty string")
    output_path = Path(output_path)
    if not output_path.parent.is_dir():
        raise FileNotFoundError(
            f"render_quality_report_pdf: parent directory missing: {output_path.parent}"
        )

    regular_path, bold_path = _fonts.resolve_korean_font_paths()
    regular_name, bold_name = _fonts.register_for_reportlab(regular_path, bold_path)

    # Patch the BodyText / Heading paragraph styles to use the registered
    # Korean face so md_parser's flowables render Korean glyphs.
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
        title="시험품질보고서",
        author=_PRODUCER,
        creator=_PRODUCER,
        producer=_PRODUCER,
    )

    def _pin_metadata(canvas, _doc):
        canvas.setProducer(_PRODUCER)
        canvas.setCreator(_PRODUCER)
        canvas.setTitle("시험품질보고서")
        canvas.setAuthor(_PRODUCER)

    with _pin_source_date_epoch(epoch):
        doc.build(flowables, onFirstPage=_pin_metadata, onLaterPages=_pin_metadata)


__all__ = ["render_quality_report_pdf"]
