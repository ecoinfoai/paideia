"""T026 / T035 — Deterministic Markdown report builder for retro-mester.

Entry point: ``build_report_md(recs, uncovered_ratio, gaps, semester, course)``.

Section (A) 회고: a table of COVERED (is_covered=True) changes ranked 1..N
with columns:

  순위 | 단원 | 집단 | 인지수준 | 원인 가설 | 덮는 학생(n) | 덮는 학생(%) | 단원무게 | 실행난이도 | 우선순위 사분면

Followed by a line stating the uncovered-gap ratio.

Section (C) 집단별 전략 (US2 T035): group-differentiated strategy tables
for 학령기 and 만학도, listing prescription per chapter gap.

When ``llm_block`` is ``None`` (US1 / no LLM path), template prose only.
No individual student names or IDs appear.
"""

from __future__ import annotations

from paideia_shared.schemas.change_recommendation import ChangeRecommendation
from paideia_shared.schemas.unit_gap import UnitGap

_TABLE_HEADERS = (
    "순위",
    "단원",
    "집단",
    "인지수준",
    "원인 가설",
    "덮는 학생(n)",
    "덮는 학생(%)",
    "단원무게",
    "실행난이도",
    "우선순위 사분면",
)


def _md_table_row(cells: tuple[str, ...]) -> str:
    """Format a Markdown table data row from a tuple of cell strings.

    Args:
        cells: Tuple of cell content strings.

    Returns:
        Markdown table row string (``| a | b | c |``).
    """
    return "| " + " | ".join(cells) + " |"


def _rec_to_table_row(rec: ChangeRecommendation) -> tuple[str, ...]:
    """Extract a tuple of display strings from a covered recommendation.

    Args:
        rec: A ChangeRecommendation with is_covered=True.

    Returns:
        Tuple of display strings matching ``_TABLE_HEADERS`` column order.
    """
    pct_str = f"{rec.covered_pct_segment * 100:.1f}%"
    return (
        str(rec.rank),
        rec.chapter,
        rec.segment,
        rec.target_cognitive_level,
        rec.cause_hypothesis,
        str(rec.covered_n),
        pct_str,
        str(rec.weight),
        rec.effort_level,
        rec.priority_quadrant,
    )


def _build_group_strategy_section(
    gaps: list[UnitGap],
    prescriptions: dict[tuple[str, str], str],
) -> list[str]:
    """Build the 집단별 전략 (US2 T035) section lines.

    Groups gaps by segment (학령기 / 만학도) and emits a sub-table per group
    showing chapter, structural flag, cause, and prescription.

    No student IDs are written.

    Args:
        gaps: All UnitGap records (both segments).
        prescriptions: Mapping (chapter, segment) → prescription string.

    Returns:
        List of Markdown line strings for section (C).
    """
    lines: list[str] = []
    lines.append("## (C) 집단별 전략")
    lines.append("")

    # Determine which segments appear in the data.
    segments_present = sorted({g.segment for g in gaps})

    for segment in segments_present:
        segment_gaps = sorted(
            [g for g in gaps if g.segment == segment],
            key=lambda g: g.chapter,
        )
        lines.append(f"### {segment}")
        lines.append("")

        if not segment_gaps:
            lines.append("해당 집단의 빈틈이 없습니다.")
            lines.append("")
            continue

        headers = ("단원", "구조적", "원인", "처방 전략")
        sep = "| " + " | ".join("---" for _ in headers) + " |"
        lines.append(_md_table_row(headers))
        lines.append(sep)

        for gap in segment_gaps:
            structural_mark = "✓" if gap.is_structural else ""
            presc = prescriptions.get((gap.chapter, gap.segment), "")
            lines.append(_md_table_row((gap.chapter, structural_mark, gap.cause, presc)))

        lines.append("")

    return lines


def build_report_md(
    recs: list[ChangeRecommendation],
    uncovered_ratio: float,
    gaps: list[UnitGap],
    semester: str,
    course: str,
    *,
    llm_block: str | None = None,
    prescriptions: dict[tuple[str, str], str] | None = None,
) -> str:
    """Build the Markdown retrospective report (US1 sections + US2 집단별 전략).

    Generates a deterministic Markdown string covering:
    - Section (A): covered recommendations ranked 1..N in a table, followed
      by a summary line for uncovered gaps.
    - Section (B): optional LLM-generated narrative (US2+ when provided).
    - Section (C): 집단별 전략 — group-differentiated strategy tables for
      each segment present in ``gaps`` (US2 T035; emitted when
      ``prescriptions`` is provided).

    No individual student names or IDs are emitted.

    Args:
        recs: Full list of ChangeRecommendation objects (covered + uncovered).
        uncovered_ratio: Fraction of gaps that remain uncovered (0..1).
        gaps: Full list of UnitGap records (used for total-gap count and
            group strategy section).
        semester: Semester code, e.g. ``"2026-1"``.
        course: Course slug, e.g. ``"anatomy"``.
        llm_block: Optional LLM-generated narrative block for US2+.
            When ``None``, section (B) is omitted.
        prescriptions: Optional mapping ``(chapter, segment) → prescription``
            for section (C).  When ``None``, section (C) is omitted.

    Returns:
        Deterministic Markdown string ready to be written to ``.md`` or
        fed to ``write_report_pdf``.
    """
    covered = sorted(
        [r for r in recs if r.is_covered],
        key=lambda r: r.rank or 999,
    )

    lines: list[str] = []

    # Title
    lines.append(f"# 학기 회고 보고서 — {semester} {course}")
    lines.append("")

    # Section (A)
    lines.append("## (A) 변경 권고 요약")
    lines.append("")

    if covered:
        # Table header
        sep_row = "| " + " | ".join("---" for _ in _TABLE_HEADERS) + " |"
        lines.append(_md_table_row(_TABLE_HEADERS))
        lines.append(sep_row)
        for rec in covered:
            lines.append(_md_table_row(_rec_to_table_row(rec)))
        lines.append("")
    else:
        lines.append("커버된 변경 권고가 없습니다.")
        lines.append("")

    # Uncovered-gap ratio line
    total_gaps = len(gaps)
    uncovered_pct = uncovered_ratio * 100
    lines.append(
        f"못 덮은 빈틈 비율 = {uncovered_pct:.1f}%"
        f" ({total_gaps}개 빈틈 중 {round(uncovered_ratio * total_gaps)}개 미처리)"
    )
    lines.append("")

    # Optional LLM block (US2+)
    if llm_block is not None:
        lines.append("## (B) 심층 분석")
        lines.append("")
        lines.append(llm_block)
        lines.append("")

    # Section (C): group-differentiated strategy (US2 T035)
    if prescriptions is not None:
        lines.extend(_build_group_strategy_section(gaps, prescriptions))

    return "\n".join(lines)


__all__ = ["build_report_md"]
