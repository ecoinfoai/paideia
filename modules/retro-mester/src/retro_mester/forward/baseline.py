"""T037 — Build baseline snapshot for forward-contract (US3).

``build_baseline`` converts per-student CombinedAnalysisRow records into
per-(segment × chapter) BaselineSnapshotRow instances.

Granularity note (research R2):
    group×chapter×item_type 3-way cross is unavailable — per-cognitive-level
    breakdown is therefore deferred.  All rows use ``cognitive_level="전체"``
    (segment × chapter overall rate).  Per-cognitive-level baseline can be
    added once immersio exposes per-item student responses.
"""

from __future__ import annotations

from paideia_shared.schemas import (
    BaselineSnapshotRow,
    CombinedAnalysisRow,
    RetroMesterConfig,
)

from retro_mester.segment.assign import assign_segments


def build_baseline(
    rows: list[CombinedAnalysisRow],
    config: RetroMesterConfig,
) -> list[BaselineSnapshotRow]:
    """Build one BaselineSnapshotRow per (segment × chapter) combination.

    Students absent from ``config.group_roster`` are excluded via
    ``assign_segments``.  For each (segment, chapter) pair the row captures:
    - ``correct_rate``: segment mean of ``chapter_correct_rates[chapter]``
      for students who have data for that chapter.
    - ``n``: count of students with valid data.
    - ``cognitive_level``: always ``"전체"`` (per-cognitive-level deferred,
      see research R2).

    Args:
        rows: All ``CombinedAnalysisRow`` records for this run.
        config: Active ``RetroMesterConfig``; provides ``group_roster`` and
            ``semester``/``course_slug`` for the output rows.

    Returns:
        List of ``BaselineSnapshotRow`` instances, one per (segment, chapter)
        pair with at least one student who has data.  Empty list when ``rows``
        is empty.
    """
    if not rows:
        return []

    buckets, _ = assign_segments(rows, config)

    # Collect chapter universe from all classified students.
    all_chapters: set[str] = set()
    for seg_rows in buckets.values():
        for row in seg_rows:
            all_chapters.update(row.chapter_correct_rates.keys())

    result: list[BaselineSnapshotRow] = []

    for segment in sorted(buckets.keys()):
        seg_rows = buckets[segment]
        for chapter in sorted(all_chapters):
            students_with_data = [r for r in seg_rows if chapter in r.chapter_correct_rates]
            if not students_with_data:
                continue

            rates = [r.chapter_correct_rates[chapter] for r in students_with_data]
            mean_rate = sum(rates) / len(rates)

            result.append(
                BaselineSnapshotRow(
                    semester=config.semester,
                    course_slug=config.course_slug,
                    segment=segment,
                    chapter=chapter,
                    # cognitive_level is fixed at "전체" — per-cognitive-level
                    # breakdown deferred until immersio exposes item-level
                    # student responses (research R2).
                    cognitive_level="전체",
                    correct_rate=mean_rate,
                    n=len(students_with_data),
                )
            )

    return result


__all__ = ["build_baseline"]
