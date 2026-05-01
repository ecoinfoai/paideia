"""Phase E human-readable report writer (T047).

Renders ``메일_발송보고서.md`` from a ``DispatchReportData`` model. Korean
status labels per contracts/email_log_csv.md ↔ DispatchStatus mapping.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import (
    CohortLabel,
    DispatchReportData,
    DispatchStatus,
)

# Single source for the English-enum → Korean-label mapping (FR-D04 / D08).
# Allowed by ADR-009 — operational labels only, no PII.
STATUS_KR: dict[DispatchStatus, str] = {
    DispatchStatus.SUCCESS: "성공",
    DispatchStatus.SKIPPED: "누락",
    DispatchStatus.FAILED: "실패",
    DispatchStatus.TEMPORARY_FAILURE: "일시실패",
    DispatchStatus.DRY_RUN: "미리보기",
    DispatchStatus.TEST_DUMMY: "테스트",
}

COHORT_KR: dict[CohortLabel, str] = {
    CohortLabel.LOW_SCORE: "저득점",
    CohortLabel.REST: "나머지",
    CohortLabel.ALL: "전체",
}


def write_dispatch_report_md(
    report_data: DispatchReportData, gold_dir: Path
) -> Path:
    """Write a Korean Markdown summary of the dispatch run.

    Args:
        report_data: Aggregated dispatch state.
        gold_dir: Output directory for ``메일_발송보고서.md``.

    Returns:
        Path to the written report.
    """
    if not isinstance(gold_dir, Path):
        raise TypeError(
            f"write_dispatch_report_md: gold_dir must be Path, got "
            f"{type(gold_dir).__name__}"
        )
    gold_dir.mkdir(parents=True, exist_ok=True)

    m = report_data.manifest
    lines: list[str] = []
    lines.append(f"# 메일 발송 보고서 — {m.semester} {m.course_slug}")
    lines.append("")
    lines.append(f"- 강좌: {m.course_name_kr}")
    lines.append(f"- 시험: {m.exam_name}")
    lines.append(f"- 발송일: {m.sent_date_kst.isoformat()}")
    lines.append(f"- 모드: {m.mode.value}")
    lines.append(f"- 프로파일: {m.profile_name} ({m.profile_kind})")
    lines.append("")
    lines.append("## 발송 결과 요약")
    lines.append("")
    lines.append("| 상태 | 인원 |")
    lines.append("|---|---:|")
    for status in DispatchStatus:
        count = report_data.summary_table.get(status, 0)
        lines.append(f"| {STATUS_KR[status]} | {count} |")
    lines.append("")

    if report_data.failed_rows:
        lines.append("## 실패 학생 명단")
        lines.append("")
        lines.append("| 학번 | 이름 | 사유 |")
        lines.append("|---|---|---|")
        for row in report_data.failed_rows:
            lines.append(
                f"| {row.student_id} | {row.name_kr} | "
                f"{row.error_kind} — {row.error_detail} |"
            )
        lines.append("")

    if report_data.skipped_rows:
        lines.append("## 누락 학생 명단")
        lines.append("")
        lines.append("| 학번 | 이름 | 사유 |")
        lines.append("|---|---|---|")
        for row in report_data.skipped_rows:
            lines.append(
                f"| {row.student_id} | {row.name_kr} | "
                f"{row.error_kind} — {row.error_detail} |"
            )
        lines.append("")

    out = gold_dir / "메일_발송보고서.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


__all__ = ["STATUS_KR", "COHORT_KR", "write_dispatch_report_md"]
