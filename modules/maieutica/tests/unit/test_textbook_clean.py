"""Unit tests for maieutica.ingest.textbook_clean — T019.

TDD: failing tests written BEFORE implementation (RED → GREEN).

Covers:
- Noise removal: spaced headers, running headers, page numbers, figure/table
  captions, 연습문제 block, 참고문헌, footnotes.
- Body text and section headings are kept.
- Original line numbers preserved on kept lines.
- removed_spans audit log entries map back to ORIGINAL char offsets (verified
  by parsing the '[reason] line N: ...' format and checking the original text
  at those positions).
- Determinism: identical input → identical output.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Fixture text (mirrors examen's test fixture, adapted for anatomy chapter 8)
# ---------------------------------------------------------------------------
#
#  1: H U M A N  A N A T O M Y  &  P H Y S I O L O G Y  — spaced header
#  2: 제8장 호흡계통  — running header
#  3: C H A P T E R  8  — spaced header
#  4: 200  — page number
#  5: (blank)
#  6: 1. 호흡기의 구조  — section heading (body)
#  7: (blank)
#  8: 코는 후각과 공기 가습을 담당한다.  — body
#  9: 그림 8-1 호흡기 구조도  — figure caption
# 10: 인두는 소화계와 호흡계가 교차한다.  — body
# 11: 표 8-1 호흡기 각 부위의 기능  — table caption
# 12: (blank)
# 13: 201  — page number
# 14: (blank)
# 15: 2. 호흡운동  — section heading (body)
# 16: (blank)
# 17: 흡기 시 횡격막이 하강한다.  — body
# 18: †이 내용은 선택 학습입니다.  — footnote
# 19: (blank)
# 20: 연습문제  — exercise block start (remove from here to end)
# 21: (blank)
# 22: 1. 코의 기능을 기술하시오.  — exercise
# 23: 2. 흡기 기전을 설명하시오.  — exercise

FIXTURE_LINES: list[str] = [
    "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y",  # 1
    "제8장 호흡계통",  # 2
    "C H A P T E R  8",  # 3
    "200",  # 4
    "",  # 5
    "1. 호흡기의 구조",  # 6
    "",  # 7
    "코는 후각과 공기 가습을 담당한다.",  # 8
    "그림 8-1 호흡기 구조도",  # 9
    "인두는 소화계와 호흡계가 교차한다.",  # 10
    "표 8-1 호흡기 각 부위의 기능",  # 11
    "",  # 12
    "201",  # 13
    "",  # 14
    "2. 호흡운동",  # 15
    "",  # 16
    "흡기 시 횡격막이 하강한다.",  # 17
    "†이 내용은 선택 학습입니다.",  # 18
    "",  # 19
    "연습문제",  # 20
    "",  # 21
    "1. 코의 기능을 기술하시오.",  # 22
    "2. 흡기 기전을 설명하시오.",  # 23
]


def _clean(lines: list[str]) -> tuple[list[tuple[int, str]], list[str]]:
    """Helper: import and run clean_textbook."""
    from maieutica.ingest.textbook_clean import clean_textbook

    return clean_textbook(lines)


# ============================================================================
# Noise removal
# ============================================================================


class TestNoiseRemoval:
    def test_spaced_letter_header_removed(self) -> None:
        """Lines like 'H U M A N  A N A T O M Y' are removed."""
        kept, _ = _clean(FIXTURE_LINES)
        kept_texts = {text for _, text in kept}
        assert "H U M A N  A N A T O M Y  &  P H Y S I O L O G Y" not in kept_texts
        assert "C H A P T E R  8" not in kept_texts

    def test_spaced_header_in_removed_spans(self) -> None:
        """Removed spaced headers appear in removed_spans."""
        _, removed = _clean(FIXTURE_LINES)
        assert any("spaced" in r.lower() or "header" in r.lower() for r in removed)

    def test_running_header_removed(self) -> None:
        """'제8장 호흡계통' (running header) is removed."""
        kept, _ = _clean(FIXTURE_LINES)
        assert "제8장 호흡계통" not in {t for _, t in kept}

    def test_running_header_in_removed_spans(self) -> None:
        """Removed running header appears in removed_spans."""
        _, removed = _clean(FIXTURE_LINES)
        assert any("running" in r.lower() or "header" in r.lower() for r in removed)

    def test_page_numbers_removed(self) -> None:
        """Standalone digit lines ('200', '201') are removed."""
        kept, _ = _clean(FIXTURE_LINES)
        kept_texts = {t for _, t in kept}
        assert "200" not in kept_texts
        assert "201" not in kept_texts

    def test_page_numbers_in_removed_spans(self) -> None:
        """Removed page numbers appear in removed_spans."""
        _, removed = _clean(FIXTURE_LINES)
        assert any("page" in r.lower() or "number" in r.lower() for r in removed)

    def test_figure_caption_removed(self) -> None:
        """'그림 8-1 …' (figure caption) is removed."""
        kept, _ = _clean(FIXTURE_LINES)
        assert "그림 8-1 호흡기 구조도" not in {t for _, t in kept}

    def test_table_caption_removed(self) -> None:
        """'표 8-1 …' (table caption) is removed."""
        kept, _ = _clean(FIXTURE_LINES)
        assert "표 8-1 호흡기 각 부위의 기능" not in {t for _, t in kept}

    def test_captions_in_removed_spans(self) -> None:
        """Removed figure/table captions appear in removed_spans."""
        _, removed = _clean(FIXTURE_LINES)
        assert any(
            "caption" in r.lower() or "그림" in r or "표" in r for r in removed
        )

    def test_footnote_removed(self) -> None:
        """Lines starting with '†' (footnote marker) are removed."""
        kept, _ = _clean(FIXTURE_LINES)
        assert "†이 내용은 선택 학습입니다." not in {t for _, t in kept}

    def test_footnote_in_removed_spans(self) -> None:
        """Removed footnote appears in removed_spans."""
        _, removed = _clean(FIXTURE_LINES)
        assert any("footnote" in r.lower() or "각주" in r for r in removed)

    def test_exercise_block_removed(self) -> None:
        """From '연습문제' to end of input is removed."""
        kept, _ = _clean(FIXTURE_LINES)
        kept_texts = {t for _, t in kept}
        assert "연습문제" not in kept_texts
        assert "1. 코의 기능을 기술하시오." not in kept_texts
        assert "2. 흡기 기전을 설명하시오." not in kept_texts

    def test_exercise_block_in_removed_spans(self) -> None:
        """연습문제 block appears in removed_spans."""
        _, removed = _clean(FIXTURE_LINES)
        assert any("연습문제" in r or "exercise" in r.lower() for r in removed)


# ============================================================================
# Body text preservation
# ============================================================================


class TestBodyPreservation:
    def test_body_text_kept(self) -> None:
        """Body text lines survive cleaning."""
        kept, _ = _clean(FIXTURE_LINES)
        kept_texts = {t for _, t in kept}
        assert "코는 후각과 공기 가습을 담당한다." in kept_texts
        assert "인두는 소화계와 호흡계가 교차한다." in kept_texts
        assert "흡기 시 횡격막이 하강한다." in kept_texts

    def test_section_headings_kept(self) -> None:
        """Numbered section headings survive cleaning."""
        kept, _ = _clean(FIXTURE_LINES)
        kept_texts = {t for _, t in kept}
        assert "1. 호흡기의 구조" in kept_texts
        assert "2. 호흡운동" in kept_texts

    def test_blank_lines_kept(self) -> None:
        """Blank lines (structure markers) are kept."""
        kept, _ = _clean(FIXTURE_LINES)
        blank_lines = [(ln, t) for ln, t in kept if t == ""]
        assert len(blank_lines) > 0


# ============================================================================
# Original line number preservation
# ============================================================================


class TestLineNumberPreservation:
    def test_original_line_numbers_on_kept_lines(self) -> None:
        """Kept lines carry their ORIGINAL 1-based line numbers."""
        kept, _ = _clean(FIXTURE_LINES)
        line_map = {t: ln for ln, t in kept}

        # "코는 후각과 공기 가습을 담당한다." is FIXTURE_LINES[7] → original line 8
        assert line_map.get("코는 후각과 공기 가습을 담당한다.") == 8

        # "인두는 소화계와 호흡계가 교차한다." is FIXTURE_LINES[9] → original line 10
        assert line_map.get("인두는 소화계와 호흡계가 교차한다.") == 10

        # "흡기 시 횡격막이 하강한다." is FIXTURE_LINES[16] → original line 17
        assert line_map.get("흡기 시 횡격막이 하강한다.") == 17

    def test_removed_spans_reference_original_lines(self) -> None:
        """removed_spans entries reference original (1-based) line numbers.

        Specifically: '그림 8-1 호흡기 구조도' is at original line 9.
        The removed_span entry for this caption must contain '9'.
        """
        _, removed = _clean(FIXTURE_LINES)
        # Find the figure caption entry
        caption_spans = [r for r in removed if "그림" in r]
        assert len(caption_spans) >= 1, f"No figure-caption span found: {removed}"
        # The span must reference original line 9
        assert any("9" in span for span in caption_spans), (
            f"Line 9 not referenced in caption spans: {caption_spans}"
        )


# ============================================================================
# Char-offset audit: removed_spans → original text verification
# ============================================================================


class TestRemovedSpanCharOffsets:
    """Verify that removed_spans offsets point back to the original text.

    The '[reason] line N: ...' format lets the caller reconstruct the char
    offset of the removed text in the original file.  We parse N and verify
    that FIXTURE_LINES[N-1] matches what was removed.
    """

    def test_figure_caption_original_text_at_span_line(self) -> None:
        """The removed figure-caption span's line number points at the caption."""
        import re

        _, removed = _clean(FIXTURE_LINES)
        caption_spans = [r for r in removed if "그림" in r or "figure" in r.lower()]
        assert caption_spans, f"No figure-caption span: {removed}"

        # Parse the first span: "[reason] line N: 'text'"
        span = caption_spans[0]
        m = re.search(r"line (\d+)", span)
        assert m, f"No 'line N' in span: {span}"
        lineno = int(m.group(1))

        # The original text at that line number must be the figure caption
        original_text = FIXTURE_LINES[lineno - 1]
        assert original_text == "그림 8-1 호흡기 구조도", (
            f"Original text at line {lineno}: {original_text!r}"
        )

    def test_page_number_original_text_at_span_line(self) -> None:
        """The removed page-number span's line number points at the page number."""
        import re

        _, removed = _clean(FIXTURE_LINES)
        pn_spans = [r for r in removed if "page" in r.lower() or "number" in r.lower()]
        assert pn_spans, f"No page-number span: {removed}"

        # Parse the first page-number span
        span = pn_spans[0]
        m = re.search(r"line (\d+)", span)
        assert m, f"No 'line N' in span: {span}"
        lineno = int(m.group(1))

        # The original text at that line number must be a standalone digit
        original_text = FIXTURE_LINES[lineno - 1]
        assert original_text.strip().isdigit(), (
            f"Expected digit-only at line {lineno}, got: {original_text!r}"
        )


# ============================================================================
# Edge cases
# ============================================================================


class TestEdgeCases:
    def test_empty_input_returns_empty(self) -> None:
        """Empty input produces empty output without raising."""
        kept, removed = _clean([])
        assert kept == []
        assert removed == []

    def test_deterministic_output(self) -> None:
        """Calling clean_textbook twice produces identical results."""
        r1 = _clean(FIXTURE_LINES)
        r2 = _clean(FIXTURE_LINES)
        assert r1 == r2

    def test_references_section_removed(self) -> None:
        """'참고문헌' and subsequent lines are removed."""
        lines = [
            "본문 텍스트.",
            "참고문헌",
            "1. Kim, J. (2020). Anatomy.",
        ]
        kept, removed = _clean(lines)
        kept_texts = {t for _, t in kept}
        assert "참고문헌" not in kept_texts
        assert "1. Kim, J. (2020). Anatomy." not in kept_texts
        assert any("참고문헌" in r or "reference" in r.lower() for r in removed)

    def test_exercise_sentence_in_body_not_removed(self) -> None:
        """A body sentence starting '연습문제' is not a block heading → kept."""
        lines = [
            "연습문제는 학습에 매우 중요하다.",
            "본문 계속.",
        ]
        kept, _ = _clean(lines)
        assert "연습문제는 학습에 매우 중요하다." in {t for _, t in kept}

    @pytest.mark.parametrize(
        "heading",
        [
            "연습 문제",
            "연습문제:",
            "[연습문제]",
            "■ 연습문제",
            "연습문제 (5문항)",
        ],
    )
    def test_exercise_variants_trigger_block_removal(self, heading: str) -> None:
        """Common 연습문제 heading variants trigger block removal."""
        lines = ["본문.", heading, "1. 문제."]
        kept, removed = _clean(lines)
        assert heading not in {t for _, t in kept}
        assert "1. 문제." not in {t for _, t in kept}
        assert any("exercise" in r.lower() or "연습" in r for r in removed)
