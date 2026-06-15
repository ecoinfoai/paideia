"""T026 / T035 / T042 — Deterministic Markdown report builder for retro-mester.

Entry point: ``build_report_md(recs, uncovered_ratio, gaps, semester, course)``.

Section (A) 회고: a table of COVERED (is_covered=True) changes ranked 1..N
with columns:

  순위 | 단원 | 집단 | 인지수준 | 원인 가설 | 덮는 학생(n) | 덮는 학생(%) | 단원무게 | 실행난이도 | 우선순위 사분면

Followed by a line stating the uncovered-gap ratio.

Section (B) 내년 준비 예견 (US3 T042): carry-forward cohort traits and ledger
summary; optional 작년 변경 효과감사 subsection when audit data is present.
FR-016: explicitly states NO micro YoY extrapolation.

Section (C) 집단별 전략 (US2 T035): group-differentiated strategy tables
for 학령기 and 만학도, listing prescription per chapter gap.

When ``llm_block`` is ``None`` (US1 / no LLM path), template prose only.
No individual student names or IDs appear.
"""

from __future__ import annotations

from paideia_shared.schemas.alignment_finding import AlignmentFinding
from paideia_shared.schemas.change_recommendation import ChangeRecommendation
from paideia_shared.schemas.retro_forward import ImprovementLedgerEntry
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


def _build_forward_section(
    ledger: list[ImprovementLedgerEntry],
    audit: dict | None,
    gaps: list[UnitGap],
) -> list[str]:
    """Build section (B) 내년 준비 예견 (US3 T042).

    Emits:
    - Coarse cohort trait carry-forward prose (FR-016 compliant — no micro
      YoY extrapolation).
    - Ledger summary table (entry_id, chapter, segment, baseline, target).
    - Optional '작년 변경 효과감사' subsection when audit is provided.

    FR-016: This section explicitly states that no micro year-over-year
    extrapolation is performed.  Trends are described only at the coarse
    cohort level (e.g. heterogeneous mix assumption).

    Args:
        ledger: Improvement ledger entries for next year.
        audit: Optional audit dict from ``audit_prior``.  ``None`` → cold-start.
        gaps: Current-year gaps for cohort trait inference.

    Returns:
        List of Markdown line strings.
    """
    lines: list[str] = []
    lines.append("## (B) 내년 준비 예견")
    lines.append("")

    # FR-016 disclaimer
    lines.append(
        "> **주의**: 본 절은 연도간 미시적 외삽(YoY extrapolation)을 수행하지 않습니다.  "
    )
    lines.append(
        "> 코호트 특성은 현재 학기 데이터에서 추론한 조건부 가정이며, "
        "다음 학기 실제 코호트와 다를 수 있습니다."
    )
    lines.append("")

    # Coarse cohort trait carry-forward
    is_structural_any = any(g.is_structural for g in gaps)
    segments_present = sorted({g.segment for g in gaps})
    multi_segment = len(segments_present) > 1

    lines.append("### 코호트 특성 이월 가정")
    lines.append("")
    if multi_segment:
        lines.append(
            f"이질혼합(bio-weak·{'/'.join(segments_present)}) 구조가 "
            "차년도에도 유지될 것으로 가정합니다."
        )
    else:
        lines.append("단일 집단 구조가 차년도에도 유지될 것으로 가정합니다.")
    if is_structural_any:
        lines.append(
            "구조적 빈틈이 확인되었습니다 — 교수법·교재 수준 개선 없이는 "
            "다음 학기에도 유사한 패턴이 나타날 수 있습니다."
        )
    lines.append("")

    # Ledger summary table
    lines.append("### 개선 서약 요약")
    lines.append("")
    if ledger:
        hdr = ("서약 ID", "단원", "집단", "현 기준치", "목표치", "측정 시점")
        sep = "| " + " | ".join("---" for _ in hdr) + " |"
        lines.append("| " + " | ".join(hdr) + " |")
        lines.append(sep)
        for e in ledger:
            lines.append(
                "| "
                + " | ".join([
                    e.entry_id[:8] + "…",
                    e.chapter,
                    e.segment,
                    f"{e.baseline_value:.2f}",
                    f"{e.target_value:.2f}",
                    e.measure_at,
                ])
                + " |"
            )
        lines.append("")
    else:
        lines.append("개선 서약 없음 (커버된 권고 없음).")
        lines.append("")

    # Optional audit subsection
    if audit is not None:
        lines.append("### 작년 변경 효과감사")
        lines.append("")
        prior_year = audit.get("prior_year", "N/A")
        lines.append(f"기준: {prior_year} 학기 서약")
        lines.append("")
        results = audit.get("results", [])
        if results:
            ahdr = ("서약 ID", "이전 기준치", "목표치", "금년 실제값", "달성")
            asep = "| " + " | ".join("---" for _ in ahdr) + " |"
            lines.append("| " + " | ".join(ahdr) + " |")
            lines.append(asep)
            for r in results:
                this_val = r.get("this_year_value")
                val_str = f"{this_val:.2f}" if this_val is not None else "N/A"
                met_str = "✓" if r.get("met") else "✗"
                eid = str(r.get("entry_id", ""))
                lines.append(
                    "| "
                    + " | ".join([
                        eid[:8] + "…" if len(eid) > 8 else eid,
                        f"{r.get('prior_baseline', 0.0):.2f}",
                        f"{r.get('prior_target', 0.0):.2f}",
                        val_str,
                        met_str,
                    ])
                    + " |"
                )
            lines.append("")
        else:
            lines.append("감사 결과 없음.")
            lines.append("")

    return lines


def _build_alignment_section(
    findings: list[AlignmentFinding],
) -> list[str]:
    """Build section (D) 인지수준·정렬 (US4 T047).

    Emits a table of alignment findings with chapter, flag, taught/tested counts,
    and learned_rate.  Cliffs are highlighted in the note column.

    Args:
        findings: AlignmentFinding list from build_alignment.

    Returns:
        List of Markdown line strings.
    """
    lines: list[str] = []
    lines.append("## (D) 인지수준·정렬")
    lines.append("")
    lines.append(
        "각 단원의 교수-평가 정렬 상태와 인지수준 분포를 요약합니다.  "
        "'인지수준절벽'은 지식축적 대비 이해·적용 수준의 정답률이 크게 낮은 경우입니다."
    )
    lines.append("")

    if not findings:
        lines.append("정렬 분석 데이터가 없습니다.")
        lines.append("")
        return lines

    headers = ("단원", "정렬 플래그", "교수주차", "출제문항", "코호트 정답률")
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    lines.append("| " + " | ".join(headers) + " |")
    lines.append(sep)

    for f in sorted(findings, key=lambda x: x.chapter):
        lines.append(
            "| "
            + " | ".join([
                f.chapter,
                f.flag,
                str(f.taught_weeks),
                str(f.tested_items),
                f"{f.learned_rate:.2f}",
            ])
            + " |"
        )

    lines.append("")

    # Cliff chapters summary
    cliff_chapters = [f.chapter for f in findings if f.flag == "인지수준절벽"]
    if cliff_chapters:
        lines.append("**인지수준절벽 단원:**")
        for ch in sorted(cliff_chapters):
            f = next(x for x in findings if x.chapter == ch)
            profile_str = ", ".join(
                f"{t}: {r:.2f}" for t, r in sorted(f.cognitive_profile.items())
            )
            lines.append(f"- {ch}: 인지수준별 정답률 [{profile_str}]")
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
    forward_ledger: list[ImprovementLedgerEntry] | None = None,
    forward_audit: dict | None = None,
    alignment_findings: list[AlignmentFinding] | None = None,
) -> str:
    """Build the Markdown retrospective report (US1 + US2 + US3 sections).

    Generates a deterministic Markdown string covering:
    - Section (A): covered recommendations ranked 1..N in a table, followed
      by a summary line for uncovered gaps.
    - Section (B): 내년 준비 예견 (US3 T042) — emitted when
      ``forward_ledger`` is provided.  Includes optional 작년 변경 효과감사
      subsection when ``forward_audit`` is not ``None``.
      FR-016: explicitly states no micro YoY extrapolation.
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
            When ``None``, section (B) LLM prose is omitted.
        prescriptions: Optional mapping ``(chapter, segment) → prescription``
            for section (C).  When ``None``, section (C) is omitted.
        forward_ledger: Optional list of ``ImprovementLedgerEntry`` instances
            for section (B).  When ``None``, section (B) is omitted.
        forward_audit: Optional audit dict from ``audit_prior``.  Included in
            section (B) as 작년 변경 효과감사.  Ignored when
            ``forward_ledger`` is ``None``.
        alignment_findings: Optional list of ``AlignmentFinding`` for section
            (D) 인지수준·정렬 (US4 T047).  When ``None``, section (D) is omitted.

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

    # Section (B): 내년 준비 예견 (US3 T042)
    if forward_ledger is not None:
        lines.extend(_build_forward_section(forward_ledger, forward_audit, gaps))

    # Optional LLM block (reserved for future US)
    if llm_block is not None:
        lines.append("## (B-LLM) 심층 분석")
        lines.append("")
        lines.append(llm_block)
        lines.append("")

    # Section (C): group-differentiated strategy (US2 T035)
    if prescriptions is not None:
        lines.extend(_build_group_strategy_section(gaps, prescriptions))

    # Section (D): 인지수준·정렬 (US4 T047)
    if alignment_findings is not None:
        lines.extend(_build_alignment_section(alignment_findings))

    return "\n".join(lines)


__all__ = ["build_report_md"]
