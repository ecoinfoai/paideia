"""Structural gap escalation for retro-mester US2 (T032).

SC-004: When the baseline segment's mean correct rate on a chapter is ALSO
below ``config.gap_threshold``, ALL gaps for that chapter are marked
``is_structural=True``.  This signals that the difficulty is not
segment-specific but reflects a curriculum/instruction-level problem.

Rationale (research R3):
  A gap confined to one segment may reflect a demographic readiness
  difference; when even the reference baseline struggles, the root cause
  is more likely structural (teaching delivery or material complexity).
"""

from __future__ import annotations

from paideia_shared.schemas import CombinedAnalysisRow, RetroMesterConfig, UnitGap

from retro_mester.segment.assign import assign_segments


def escalate_structural(
    gaps: list[UnitGap],
    rows: list[CombinedAnalysisRow],
    config: RetroMesterConfig,
) -> list[UnitGap]:
    """Set ``is_structural=True`` on gaps whose chapter also stumps the baseline.

    For each chapter with at least one gap, compute the baseline segment's
    mean correct rate.  If that rate is strictly below ``config.gap_threshold``
    (and at least one baseline student has data for the chapter), all gaps for
    that chapter are rebuilt with ``is_structural=True``.  Chapters where the
    baseline segment is at or above the threshold remain ``is_structural=False``.

    UnitGap is frozen (immutable Pydantic model), so escalated gaps are rebuilt
    via ``model_copy(update=...)`` — original objects are never mutated.

    Args:
        gaps: Detected ``UnitGap`` instances (``is_structural=False`` from US1).
        rows: All ``CombinedAnalysisRow`` records for the run.
        config: Active ``RetroMesterConfig``; provides ``baseline_segment`` and
            ``gap_threshold``.

    Returns:
        New list of ``UnitGap`` instances with ``is_structural`` correctly set.
        Order mirrors the input ``gaps`` list.
    """
    if not gaps:
        return []

    baseline_seg = config.baseline_segment
    threshold = config.gap_threshold

    # Partition rows into per-segment buckets for baseline lookup.
    buckets, _ = assign_segments(rows, config)
    baseline_rows = buckets.get(baseline_seg, [])

    # Collect the chapter universe present in the gaps.
    chapters = {g.chapter for g in gaps}

    # For each chapter, compute whether the baseline segment is also below threshold.
    structural_chapters: set[str] = set()
    for chapter in chapters:
        students_with_data = [row for row in baseline_rows if chapter in row.chapter_correct_rates]
        if not students_with_data:
            # No baseline data for this chapter — cannot confirm structural.
            continue

        rates = [row.chapter_correct_rates[chapter] for row in students_with_data]
        baseline_mean = sum(rates) / len(rates)

        if baseline_mean < threshold:
            structural_chapters.add(chapter)

    # Rebuild gaps, escalating those in structural chapters.
    result: list[UnitGap] = []
    for gap in gaps:
        if gap.chapter in structural_chapters and not gap.is_structural:
            result.append(gap.model_copy(update={"is_structural": True}))
        else:
            result.append(gap)

    return result


__all__ = ["escalate_structural"]
