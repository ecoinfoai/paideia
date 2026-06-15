"""Segment assignment for retro-mester analysis (T021, US1).

Partitions CombinedAnalysisRow records into per-segment buckets using the
``group_roster`` from RetroMesterConfig.  Students not listed in the roster
are excluded from all segment buckets and returned separately as ``unclassified``.

US2 (T031) will extend this module to designate the baseline segment and
support multi-cohort comparisons.
"""

from __future__ import annotations

from collections import defaultdict

from paideia_shared.schemas import CombinedAnalysisRow, RetroMesterConfig
from paideia_shared.schemas.retro_common import SegmentKey


def assign_segments(
    rows: list[CombinedAnalysisRow],
    config: RetroMesterConfig,
) -> tuple[dict[SegmentKey, list[CombinedAnalysisRow]], list[str]]:
    """Partition rows into per-segment buckets using the roster.

    Students not present in ``config.group_roster`` are placed in the
    ``unclassified`` list and are **not** included in any segment bucket.
    Downstream gap detection must operate only on classified students.

    US2 note: baseline designation (``config.baseline_segment``) and multi-cohort
    handling will be wired here in T031.

    Args:
        rows: All ``CombinedAnalysisRow`` records loaded for this run.
        config: Active ``RetroMesterConfig`` carrying ``group_roster``.

    Returns:
        A two-tuple ``(buckets, unclassified)`` where:
        - ``buckets``: mapping from ``SegmentKey`` to list of matching rows
          (keys only present when at least one student maps to that segment).
        - ``unclassified``: list of ``student_id`` strings for students whose
          IDs are absent from ``group_roster``.
    """
    buckets: dict[SegmentKey, list[CombinedAnalysisRow]] = defaultdict(list)
    unclassified: list[str] = []

    for row in rows:
        segment = config.group_roster.get(row.student_id)
        if segment is None:
            unclassified.append(row.student_id)
        else:
            buckets[segment].append(row)

    return dict(buckets), unclassified


__all__ = ["assign_segments"]
