"""Phase E human-readable report writer (T047).

Renders ``메일_발송보고서.md`` from a ``DispatchReportData`` model. Korean
status labels per contracts/email_log_csv.md ↔ DispatchStatus mapping.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.io import atomic_write
from paideia_shared.schemas import (
    CohortLabel,
    DispatchReportData,
    DispatchStatus,
)

from .log import RetryMode

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
    report_data: DispatchReportData,
    gold_dir: Path,
    *,
    filename: str = "메일_발송보고서.md",
    retry_mode: RetryMode | None = None,
    failed_skipped_count: int = 0,
) -> Path:
    """Write a Korean Markdown summary of the dispatch run.

    Args:
        report_data: Aggregated dispatch state.
        gold_dir: Output directory for the report file.
        filename: Report filename within ``gold_dir``. Defaults to
            ``메일_발송보고서.md`` (send-mode). v0.1.1 dry-run callers pass
            ``메일_발송보고서_dryrun.md`` so the send-mode report file is
            never overwritten by a dry-run (contracts/dry_run_outputs.md §2,
            FR-C03b/c).
        retry_mode: Effective ``RetryMode`` for this run (CLI flag → enum).
            When ``RetryMode.RETRY_SKIPPED`` *and* ``failed_skipped_count``
            ≥ 1, an extra v0.1.1 behaviour-change notice line is appended
            to the report so the operator sees that ``failed``-status
            students are now skipped under ``--retry-skipped`` (SC-008,
            spec.md Edge Cases / FR-C04f). Default ``None`` → no notice.
        failed_skipped_count: Number of students whose v0.1.1 priority
            winner status is ``FAILED`` and who were therefore skipped
            under the ``--retry-skipped`` retry semantics (computed by
            the pipeline against ``_latest_status_by_sid``). Only used
            when ``retry_mode == RetryMode.RETRY_SKIPPED``.

    Returns:
        Path to the written report.
    """
    if not isinstance(gold_dir, Path):
        raise TypeError(
            f"write_dispatch_report_md: gold_dir must be Path, got {type(gold_dir).__name__}"
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

    # v0.1.1 동작 변화 안내 (SC-008, spec.md Edge Cases / FR-C04f).
    # ALLOW_HARDCODING: operational notice template — no student PII.
    # ``--retry-skipped`` 모드에서 우선순위 결정 결과 ``failed`` 상태인
    # 학번이 1 개 이상이면 운영자에게 그 인원이 *건너뜀(skip)* 되었음을
    # 명시한다. v0.1.0 에서는 timestamp-only 키로 인해 같은 학번이
    # ``skipped`` 로 분류되어 재시도되었으나, v0.1.1 priority+timestamp
    # 키 하에서는 ``failed`` 가 winner 가 되고 ``--retry-skipped`` 의
    # skip_statuses 에 포함되어 건너뛴다 — 운영자가 ``--retry-failed``
    # 모드를 명시적으로 사용해야 재시도 가능.
    if retry_mode == RetryMode.RETRY_SKIPPED and failed_skipped_count >= 1:
        prefix = "v0.1.1 동작 변화: 발송 실패(failed) 상태인 학생 "  # noqa: E501  # ALLOW_HARDCODING: notice
        middle = f"{failed_skipped_count}명은 건너뜀(skip) — "
        suffix = "`--retry-failed` 모드를 사용해야 재시도됩니다."
        lines.append(prefix + middle + suffix)
        lines.append("")

    if report_data.failed_rows:
        lines.append("## 실패 학생 명단")
        lines.append("")
        lines.append("| 학번 | 이름 | 사유 |")
        lines.append("|---|---|---|")
        for row in report_data.failed_rows:
            lines.append(
                f"| {row.student_id} | {row.name_kr} | {row.error_kind} — {row.error_detail} |"
            )
        lines.append("")

    if report_data.skipped_rows:
        lines.append("## 누락 학생 명단")
        lines.append("")
        lines.append("| 학번 | 이름 | 사유 |")
        lines.append("|---|---|---|")
        for row in report_data.skipped_rows:
            lines.append(
                f"| {row.student_id} | {row.name_kr} | {row.error_kind} — {row.error_detail} |"
            )
        lines.append("")

    out = gold_dir / filename
    _text = "\n".join(lines) + "\n"
    atomic_write(out, lambda p, _t=_text: p.write_text(_t, encoding="utf-8"))
    return out


__all__ = ["STATUS_KR", "COHORT_KR", "write_dispatch_report_md"]
