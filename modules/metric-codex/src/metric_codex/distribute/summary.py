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
    codex_sids: list[str],
    roster_sids: set[str],
    per_advisor: dict[str, list[str]],
) -> AdvisorBundleSummary:
    """Construct a validated AdvisorBundleSummary from the codex student set.

    Derives all counts from the authoritative codex student set (MC-U23), not
    from the on-disk md count.  This ensures stale or missing Gold mds do not
    corrupt the arithmetic.

    The two model invariants are satisfied by construction:
    - ``assigned_count + len(unassigned_sids) == total_students_with_codex``
    - ``sum(per_advisor_counts.values()) == assigned_count``
    - ``unassigned_sids`` is ASC-sorted.

    Args:
        codex_sids: Sorted distinct student_ids in the Silver codex — the
            authoritative total.
        roster_sids: Set of student_ids that have a roster (advisor) assignment.
        per_advisor: ``{advisor_id: [list of assigned student_ids]}`` for every
            advisor; the advisor_id cardinality and per-advisor counts are
            derived from this.

    Returns:
        Validated :class:`AdvisorBundleSummary`.
    """
    total = len(codex_sids)
    # Unassigned = codex students with no roster entry, ASC-sorted.
    unassigned_sids = sorted(sid for sid in codex_sids if sid not in roster_sids)
    assigned_count = total - len(unassigned_sids)
    # per_advisor_counts: count students per advisor based on the codex set.
    per_advisor_counts = {adv: len(sids) for adv, sids in per_advisor.items() if sids}
    advisor_count = len(per_advisor_counts)

    return AdvisorBundleSummary(
        total_students_with_codex=total,
        assigned_count=assigned_count,
        unassigned_sids=unassigned_sids,
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
        unassigned: Unassigned student_ids, already ASC-sorted by
            :func:`group_by_advisor`.
        names: ``{student_id: name_kr | None}`` — names are displayed when
            known, ``"(이름 미확인)"`` otherwise.
    """
    gold_dir.mkdir(parents=True, exist_ok=True)

    if unassigned:
        lines = ["# 미배정 학생\n\n"]
        for sid in unassigned:
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


def write_missing_gold_report(
    *,
    gold_dir: Path,
    missing_sids: list[str],
    names: dict[str, str | None],
) -> None:
    """Write ``gold_dir/미생성.md`` listing assigned students with no Gold md.

    Written unconditionally when ``missing_sids`` is non-empty.  Each entry is
    an assigned codex student whose Gold md was not found during distribute (MC-U21).

    Args:
        gold_dir: The Gold-layer directory for the semester/course.
        missing_sids: ASC-sorted student_ids that are assigned (in roster) but
            have no corresponding Gold md file.
        names: ``{student_id: name_kr | None}`` — names are displayed when
            known, ``"(이름 미확인)"`` otherwise.
    """
    if not missing_sids:
        return

    gold_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Gold md 미생성 배정학생\n\n"]
    for sid in missing_sids:
        name = names.get(sid)
        display = name if name else "(이름 미확인)"
        lines.append(f"- {sid} {display}\n")
    content = "".join(lines)
    report_path = gold_dir / "미생성.md"

    def _write(tmp: Path) -> None:
        tmp.write_text(content, encoding="utf-8")

    atomic_write(report_path, _write)


__all__ = ["build_summary", "write_missing_gold_report", "write_unassigned_report"]
