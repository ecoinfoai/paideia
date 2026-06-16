"""Cohort split filter — US6 (T100j).

Reads ``학생지표.parquet`` (Phase 2 silver), classifies students into
``LOW_SCORE`` (``score_percent < 60``) or ``REST`` (``score_percent ≥ 60``),
and writes the silver parquet pair + 3 명단 markdown files. Students
with ``score_percent is None`` are *excluded from both cohorts* (per
FR-H04) and reported separately as ``score_unavailable``.

ADR-006 (운영 정책 결정): the 60-point cutoff is hard-coded — operator
policy decision baked into v0.1.0. ADR-009 explicit allow-listed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from paideia_shared.schemas import (
    CohortLabel,
    CohortRow,
    EmailMappingEntry,
)

# ADR-006 / ADR-009 — operator-policy threshold. Hard-coded constant
# (v0.1.0 commitment); changing it is a spec amendment.
SCORE_THRESHOLD_PCT_100 = 60  # ALLOW_HARDCODING: ADR-006 operator policy threshold

# Korean labels for cohort partition file names + md headings.
# ADR-009 allowlist — operational labels, not student PII.
_COHORT_KR_NAME: dict[CohortLabel, str] = {
    CohortLabel.LOW_SCORE: "저득점",
    CohortLabel.REST: "나머지",
    CohortLabel.ALL: "전체",
}


class CohortError(RuntimeError):
    """Raised on cohort filter inputs (missing metrics file, invalid cohort)."""


@dataclass(frozen=True)
class CohortFilterResult:
    """Outcome of ``filter_by_cohort``.

    Attributes:
        keep_entries: ``EmailMappingEntry`` rows whose student is in the
            requested cohort (or 'all').
        low_rows: ``CohortRow`` instances for students with score < 60.
        rest_rows: ``CohortRow`` instances for students with score ≥ 60.
        unavailable_sids: student_ids whose ``score_percent is None``.
            Always reported even when caller asked for 'all' — these
            students get a per-row ``score_unavailable`` log entry
            downstream.
    """

    keep_entries: list[EmailMappingEntry]
    low_rows: list[CohortRow]
    rest_rows: list[CohortRow]
    unavailable_sids: list[str]


def _read_metrics(
    student_metrics_path: Path,
) -> dict[str, tuple[str, float | None]]:
    """Read ``학생지표.parquet`` → ``{student_id: (name_kr, score_percent)}``.

    Args:
        student_metrics_path: Path to the immersio Phase 2 silver
            ``학생지표.parquet``.

    Returns:
        Mapping ``student_id`` → ``(name_kr, score_percent)``. Missing
        ``name_kr`` defaults to empty string; missing ``score_percent``
        is preserved as ``None``.

    Raises:
        CohortError: When the parquet does not exist or lacks the
            required columns.
    """
    if not isinstance(student_metrics_path, Path):
        raise CohortError(
            f"student_metrics_path must be Path, got {type(student_metrics_path).__name__}"
        )
    if not student_metrics_path.is_file():
        raise CohortError(f"FR-H02: student metrics parquet not found at {student_metrics_path}")
    table = pq.read_table(student_metrics_path)
    cols = table.column_names
    missing = [c for c in ("student_id", "name_kr", "score_percent") if c not in cols]
    if missing:
        raise CohortError(
            f"student metrics parquet at {student_metrics_path} missing required columns: {missing}"
        )
    df = table.to_pydict()
    out: dict[str, tuple[str, float | None]] = {}
    for sid, name, score in zip(df["student_id"], df["name_kr"], df["score_percent"], strict=True):
        out[str(sid)] = (
            (name or "") if name is not None else "",
            float(score) if score is not None else None,
        )
    return out


def filter_by_cohort(
    mapping_entries: Iterable[EmailMappingEntry],
    student_metrics_path: Path,
    cohort: CohortLabel,
) -> CohortFilterResult:
    """Partition ``mapping_entries`` by ``score_percent`` cohort.

    Args:
        mapping_entries: Pre-loaded EmailMappingEntry list (Phase A
            output).
        student_metrics_path: Path to ``학생지표.parquet``.
        cohort: Requested cohort filter — ``LOW_SCORE`` / ``REST`` /
            ``ALL`` (default for v0.1.0 — no filter, but still reports
            cohort assignment per-student).

    Returns:
        CohortFilterResult with keep_entries, low/rest cohort rows, and
        unavailable_sids (score_percent is None).

    Raises:
        CohortError: When the metrics file is missing, malformed, or the
            cohort label is invalid.
    """
    if not isinstance(cohort, CohortLabel):
        raise CohortError(f"cohort must be CohortLabel, got {type(cohort).__name__}")

    metrics = _read_metrics(student_metrics_path)

    low_rows: list[CohortRow] = []
    rest_rows: list[CohortRow] = []
    unavailable_sids: list[str] = []
    keep_sids: set[str] = set()

    for entry in mapping_entries:
        sid = entry.student_id
        if sid not in metrics:
            # Student in mapping but not in metrics → treat as unavailable
            unavailable_sids.append(sid)
            continue
        name_kr, score = metrics[sid]
        if score is None:
            unavailable_sids.append(sid)
            continue
        # Build CohortRow with deterministic name_kr (parquet) so silver
        # row writers can sort + serialise stably.
        if score < SCORE_THRESHOLD_PCT_100:
            row = CohortRow(
                student_id=sid,
                name_kr=name_kr or "이름미상",
                score_percent=score,
                cohort=CohortLabel.LOW_SCORE,
            )
            low_rows.append(row)
            if cohort in (CohortLabel.ALL, CohortLabel.LOW_SCORE):
                keep_sids.add(sid)
        else:
            row = CohortRow(
                student_id=sid,
                name_kr=name_kr or "이름미상",
                score_percent=score,
                cohort=CohortLabel.REST,
            )
            rest_rows.append(row)
            if cohort in (CohortLabel.ALL, CohortLabel.REST):
                keep_sids.add(sid)

    low_rows.sort(key=lambda r: r.student_id)
    rest_rows.sort(key=lambda r: r.student_id)
    unavailable_sids.sort()

    keep_entries = [e for e in mapping_entries if e.student_id in keep_sids]
    return CohortFilterResult(
        keep_entries=keep_entries,
        low_rows=low_rows,
        rest_rows=rest_rows,
        unavailable_sids=unavailable_sids,
    )


def write_cohort_silver(rows: list[CohortRow], parquet_path: Path) -> None:
    """Write cohort silver parquet deterministically (ADR-008).

    Args:
        rows: Sorted CohortRow list (caller pre-sorts by student_id).
        parquet_path: Output path. Parent dir created if missing.

    Determinism levers: ``use_dictionary=False``, ``write_statistics=False``.
    """
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema(
        [
            ("student_id", pa.string()),
            ("name_kr", pa.string()),
            ("score_percent", pa.float64()),
            ("cohort", pa.string()),
        ]
    )
    table = pa.table(
        {
            "student_id": [r.student_id for r in rows],
            "name_kr": [r.name_kr for r in rows],
            "score_percent": [r.score_percent for r in rows],
            "cohort": [r.cohort.value for r in rows],
        },
        schema=schema,
    )
    pq.write_table(
        table,
        parquet_path,
        use_dictionary=False,
        write_statistics=False,
        compression="snappy",
    )


def _format_cohort_md_table(rows: list[CohortRow], heading: str) -> list[str]:
    lines: list[str] = []
    lines.append(f"## {heading} ({len(rows)}명)")
    lines.append("")
    if not rows:
        lines.append("(해당 학생 없음)")
        lines.append("")
        return lines
    lines.append("| 학번 | 이름 | 점수 |")
    lines.append("|---|---|---:|")
    for row in rows:
        lines.append(f"| {row.student_id} | {row.name_kr} | {row.score_percent:.1f} |")
    lines.append("")
    return lines


def write_cohort_md(
    low_rows: list[CohortRow],
    rest_rows: list[CohortRow],
    output_dir: Path,
) -> tuple[Path, Path, Path]:
    """Write 3 cohort markdown files: combined + low_score + rest.

    Args:
        low_rows: Sorted by student_id.
        rest_rows: Sorted by student_id.
        output_dir: Gold output dir (e.g.
            ``data/gold/immersio/2026-1-anatomy/``).

    Returns:
        Tuple of paths ``(combined_md, low_md, rest_md)``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    combined_lines: list[str] = ["# Cohort 명단", ""]
    combined_lines.extend(_format_cohort_md_table(low_rows, _COHORT_KR_NAME[CohortLabel.LOW_SCORE]))
    combined_lines.extend(_format_cohort_md_table(rest_rows, _COHORT_KR_NAME[CohortLabel.REST]))
    combined_path = output_dir / "cohort_명단.md"
    combined_path.write_text("\n".join(combined_lines) + "\n", encoding="utf-8")

    low_path = output_dir / "cohort_저득점_명단.md"
    low_path.write_text(
        "# 저득점 cohort 명단\n\n"
        + "\n".join(_format_cohort_md_table(low_rows, "저득점 (점수 < 60)"))
        + "\n",
        encoding="utf-8",
    )

    rest_path = output_dir / "cohort_나머지_명단.md"
    rest_path.write_text(
        "# 나머지 cohort 명단\n\n"
        + "\n".join(_format_cohort_md_table(rest_rows, "나머지 (점수 ≥ 60)"))
        + "\n",
        encoding="utf-8",
    )

    return combined_path, low_path, rest_path


__all__ = [
    "SCORE_THRESHOLD_PCT_100",
    "CohortError",
    "CohortFilterResult",
    "filter_by_cohort",
    "write_cohort_md",
    "write_cohort_silver",
]
