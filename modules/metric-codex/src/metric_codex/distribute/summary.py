"""T051 — AdvisorBundleSummary builder and unassigned report writer.

Provides:
- ``build_summary`` — construct a validated :class:`AdvisorBundleSummary` from
  grouping results.
- ``write_unassigned_report`` — write ``gold_dir/미배정.md`` listing every
  unassigned student; written even when the list is empty (SKIP-02).
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import AdvisorBundleSummary

from metric_codex.output.determinism import atomic_write


def build_summary(
    *,
    all_student_ids: list[str],
    per_advisor: dict[str, list[Path]],
    unassigned: list[str],
) -> AdvisorBundleSummary:
    """Construct a validated AdvisorBundleSummary from distribution results.

    The model's ``assigned_count + len(unassigned_sids) == total`` invariant is
    enforced at construction — callers must pass consistent numbers.

    Args:
        all_student_ids: Every student_id that has a Gold md file (= total).
        per_advisor: ``{advisor_id: [list of md Path]}`` from group_by_advisor.
        unassigned: Sorted list of unassigned student_ids from group_by_advisor.

    Returns:
        Validated :class:`AdvisorBundleSummary`.
    """
    total = len(all_student_ids)
    assigned_count = total - len(unassigned)
    advisor_count = sum(1 for paths in per_advisor.values() if paths)
    per_advisor_counts = {
        advisor_id: len(paths) for advisor_id, paths in per_advisor.items() if paths
    }

    return AdvisorBundleSummary(
        total_students_with_codex=total,
        assigned_count=assigned_count,
        unassigned_sids=sorted(unassigned),
        advisor_count=advisor_count,
        per_advisor_counts=per_advisor_counts,
    )


def write_unassigned_report(
    *,
    gold_dir: Path,
    unassigned: list[str],
    names: dict[str, str | None],
) -> None:
    """Write ``gold_dir/미배정.md`` listing unassigned students.

    Written unconditionally — even an empty unassigned list produces the file
    (SKIP-02: explicit acknowledgement that zero students are unassigned, rather
    than a missing file that is ambiguous with "distribute not yet run").

    Args:
        gold_dir: The Gold-layer directory for the semester/course.
        unassigned: Sorted list of unassigned student_ids.
        names: ``{student_id: name_kr | None}`` — names are displayed when
            known, ``"(이름 미확인)"`` otherwise.
    """
    gold_dir.mkdir(parents=True, exist_ok=True)

    if unassigned:
        lines = ["# 미배정 학생\n\n"]
        for sid in sorted(unassigned):
            name = names.get(sid)
            display = name if name else "(이름 미확인)"
            lines.append(f"- {sid} {display}\n")
        content = "".join(lines)
    else:
        content = "# 미배정 학생\n\n미배정 학생 없음\n"

    report_path = gold_dir / "미배정.md"

    def _write(tmp: Path) -> None:
        tmp.write_text(content, encoding="utf-8")

    atomic_write(report_path, _write)


__all__ = ["build_summary", "write_unassigned_report"]
