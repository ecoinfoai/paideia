"""T031 — RED tests for `report/md_parser.py` (research §R-05).

Self-contained Markdown → reportlab Platypus flowable parser. Five element
families per the spec:

(a) ``# / ## / ###`` headings → ``Paragraph(style=Heading{1,2,3})``
(b) ``**bold**`` / ``_italic_`` inline → reportlab inline tags ``<b>...</b>`` /
    ``<i>...</i>`` inside ``Paragraph``
(c) ``| col | col |`` → ``Table`` flowable (header row + body rows)
(d) ``![alt](path)`` → ``Image`` flowable with the file path resolved
(e) Plain paragraph → ``Paragraph(style=BodyText)``

Blank lines split blocks; unknown block kinds fall through as ``Paragraph``.
The parser MUST be deterministic — same input → same flowable list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("reportlab")

from reportlab.platypus import Image, Paragraph, Spacer, Table  # noqa: E402

from immersio.report.md_parser import parse_markdown_to_flowables  # noqa: E402


def test_h1_h2_h3_become_heading_paragraphs() -> None:
    md = "# Title\n\n## Sub\n\n### Sub-sub\n"
    flowables = parse_markdown_to_flowables(md)
    paragraphs = [f for f in flowables if isinstance(f, Paragraph)]
    assert len(paragraphs) == 3
    assert paragraphs[0].style.name == "Heading1"
    assert paragraphs[1].style.name == "Heading2"
    assert paragraphs[2].style.name == "Heading3"
    # Plain text content survives through getPlainText / .text
    assert "Title" in paragraphs[0].getPlainText()
    assert "Sub" in paragraphs[1].getPlainText()


def test_bold_inline_renders_as_b_tag() -> None:
    md = "전체 평균은 **125.35점** 입니다.\n"
    flowables = parse_markdown_to_flowables(md)
    para = next(f for f in flowables if isinstance(f, Paragraph))
    # internal text representation must contain reportlab bold tag
    assert "<b>125.35점</b>" in para.text


def test_italic_inline_renders_as_i_tag() -> None:
    md = "이는 _보통 수준_의 변별력입니다.\n"
    flowables = parse_markdown_to_flowables(md)
    para = next(f for f in flowables if isinstance(f, Paragraph))
    assert "<i>보통 수준</i>" in para.text


def test_pipe_table_becomes_table_flowable() -> None:
    md = (
        "| 지표 | 값 |\n"
        "| --- | --- |\n"
        "| 평균 | 125.35 |\n"
        "| 표준편차 | 39.55 |\n"
    )
    flowables = parse_markdown_to_flowables(md)
    tables = [f for f in flowables if isinstance(f, Table)]
    assert len(tables) == 1
    rendered = tables[0]
    # reportlab Table internal `_cellvalues` exposes the 2D matrix
    cell_values = rendered._cellvalues
    assert cell_values[0] == ["지표", "값"]
    assert cell_values[1] == ["평균", "125.35"]
    assert cell_values[2] == ["표준편차", "39.55"]


def test_image_link_becomes_image_flowable(tmp_path: Path) -> None:
    img_path = tmp_path / "fig1.png"
    # Minimal 1x1 PNG so reportlab can construct an Image flowable
    img_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c6300010000000500010d0a2db40000000049454e44ae42"
            "6082"
        )
    )
    md = f"![score histogram]({img_path})\n"
    flowables = parse_markdown_to_flowables(md)
    images = [f for f in flowables if isinstance(f, Image)]
    assert len(images) == 1
    assert str(img_path) in str(images[0].filename)


def test_plain_paragraph_falls_through_as_body_text() -> None:
    md = "이 보고서는 자동 생성됩니다.\n"
    flowables = parse_markdown_to_flowables(md)
    paragraphs = [f for f in flowables if isinstance(f, Paragraph)]
    assert len(paragraphs) == 1
    assert paragraphs[0].style.name == "BodyText"
    assert "자동 생성" in paragraphs[0].getPlainText()


def test_blank_lines_split_blocks() -> None:
    md = "첫 번째 단락.\n\n두 번째 단락.\n"
    flowables = parse_markdown_to_flowables(md)
    paragraphs = [f for f in flowables if isinstance(f, Paragraph)]
    assert len(paragraphs) == 2
    assert "첫 번째" in paragraphs[0].getPlainText()
    assert "두 번째" in paragraphs[1].getPlainText()


def test_parser_is_deterministic() -> None:
    md = "# Title\n\nSome **bold** text.\n\n| a | b |\n| - | - |\n| 1 | 2 |\n"
    a = parse_markdown_to_flowables(md)
    b = parse_markdown_to_flowables(md)
    assert len(a) == len(b)
    for fa, fb in zip(a, b):
        assert type(fa) is type(fb)
        if isinstance(fa, Paragraph):
            assert fa.text == fb.text
            assert fa.style.name == fb.style.name
        elif isinstance(fa, Table):
            assert fa._cellvalues == fb._cellvalues
        elif isinstance(fa, Spacer):
            assert (fa.width, fa.height) == (fb.width, fb.height)


def test_unknown_inline_remains_literal() -> None:
    md = "코드 `inline` 은 그대로 통과합니다.\n"
    flowables = parse_markdown_to_flowables(md)
    para = next(f for f in flowables if isinstance(f, Paragraph))
    # Backticks are preserved (no code-span support yet); should not crash
    assert "inline" in para.getPlainText()
