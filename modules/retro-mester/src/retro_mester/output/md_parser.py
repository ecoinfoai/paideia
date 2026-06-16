"""Self-contained Markdown → reportlab Platypus flowable parser.

Copied from ``immersio.report.md_parser`` (T040) and adapted for
retro-mester to avoid a cross-module runtime dependency.  Sync
manually when immersio's parser is updated.

Supported block kinds:
* ``#`` / ``##`` / ``###`` headings → ``Paragraph`` with Heading style.
* ``| col | col |`` table → ``Table`` flowable.
* ``![alt](path)`` image → ``Image`` flowable.
* Anything else → ``Paragraph(BodyText)``.

Inline: ``**bold**`` and ``_italic_`` only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.flowables import Flowable

_HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_IMAGE_PATTERN = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_TABLE_ROW_PATTERN = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP_PATTERN = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_PATTERN = re.compile(r"(?<![A-Za-z0-9])_([^_\n]+?)_(?![A-Za-z0-9])")
_TABLE_LEFT_MARGIN = 5 * mm
_TABLE_FONT_SIZE = 10
_TABLE_HEADER_FONT_SIZE = 10


def _convert_inline(text: str) -> str:
    out = _BOLD_PATTERN.sub(r"<b>\1</b>", text)
    return _ITALIC_PATTERN.sub(r"<i>\1</i>", out)


def _split_table_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.strip() for cell in inner.split("|")]


def _build_table(rows: Sequence[Sequence[str]]) -> Table:
    page_width, _ = A4
    usable = page_width - 30 * mm
    n_cols = max(len(r) for r in rows) if rows else 1
    col_width = usable / n_cols if n_cols > 0 else usable
    table = Table(
        [list(row) for row in rows],
        colWidths=[col_width] * n_cols,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), _TABLE_FONT_SIZE),
                ("FONTSIZE", (0, 0), (-1, 0), _TABLE_HEADER_FONT_SIZE),
                ("BACKGROUND", (0, 0), (-1, 0), (0.92, 0.92, 0.92)),
                ("GRID", (0, 0), (-1, -1), 0.5, (0.6, 0.6, 0.6)),
                ("LEFTPADDING", (0, 0), (-1, -1), _TABLE_LEFT_MARGIN),
                ("RIGHTPADDING", (0, 0), (-1, -1), _TABLE_LEFT_MARGIN),
            ]
        )
    )
    return table


def parse_markdown_to_flowables(
    md_text: str,
    *,
    image_base_dir: Path | None = None,
) -> list[Flowable]:
    """Parse ``md_text`` into a deterministic list of reportlab flowables.

    Args:
        md_text: Markdown source.
        image_base_dir: Base directory for relative image references.

    Returns:
        List of ``Flowable`` instances ready for ``SimpleDocTemplate.build()``.

    Raises:
        ValueError: When ``md_text`` is not a string.
    """
    if not isinstance(md_text, str):
        raise ValueError(
            f"parse_markdown_to_flowables: md_text must be str, got {type(md_text).__name__}"
        )
    styles = getSampleStyleSheet()
    flowables: list[Flowable] = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flowables.append(Spacer(1, 4 * mm))
            i += 1
            continue

        m = _HEADING_PATTERN.match(stripped)
        if m:
            level = len(m.group(1))
            text = _convert_inline(m.group(2))
            style = styles[f"Heading{level}"]
            flowables.append(Paragraph(text, style))
            i += 1
            continue

        m = _IMAGE_PATTERN.match(stripped)
        if m:
            raw_path = Path(m.group(2)).expanduser()
            if not raw_path.is_absolute() and image_base_dir is not None:
                raw_path = (image_base_dir / raw_path).resolve()
            usable_width = A4[0] - 30 * mm
            img = Image(str(raw_path))
            if img.imageWidth > usable_width:
                ratio = usable_width / float(img.imageWidth)
                img.drawWidth = usable_width
                img.drawHeight = float(img.imageHeight) * ratio
            flowables.append(img)
            i += 1
            continue

        if (
            _TABLE_ROW_PATTERN.match(line)
            and i + 1 < len(lines)
            and _TABLE_SEP_PATTERN.match(lines[i + 1])
        ):
            header = _split_table_row(line)
            i += 2
            body_rows: list[list[str]] = []
            while i < len(lines) and _TABLE_ROW_PATTERN.match(lines[i]):
                body_rows.append(_split_table_row(lines[i]))
                i += 1
            flowables.append(_build_table([header, *body_rows]))
            continue

        para_lines = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            nxt_stripped = nxt.strip()
            if not nxt_stripped:
                break
            if _HEADING_PATTERN.match(nxt_stripped):
                break
            if _IMAGE_PATTERN.match(nxt_stripped):
                break
            if (
                _TABLE_ROW_PATTERN.match(nxt)
                and i + 1 < len(lines)
                and _TABLE_SEP_PATTERN.match(lines[i + 1])
            ):
                break
            para_lines.append(nxt_stripped)
            i += 1
        text = _convert_inline(" ".join(para_lines))
        flowables.append(Paragraph(text, styles["BodyText"]))

    return flowables


__all__ = ["parse_markdown_to_flowables"]
