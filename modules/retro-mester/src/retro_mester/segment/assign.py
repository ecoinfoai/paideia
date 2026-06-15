"""Segment assignment for retro-mester analysis (T021, US1; T031 US2).

Partitions CombinedAnalysisRow records into per-segment buckets using the
``group_roster`` from RetroMesterConfig.  Students not listed in the roster
are excluded from all segment buckets and returned separately as ``unclassified``.

T031 (US2): adds ``baseline_segment`` accessor.
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


def baseline_segment(config: RetroMesterConfig) -> SegmentKey:
    """Return the designated baseline segment from config.

    The baseline segment is used as the reference point for structural
    escalation (T032): when the baseline segment is also below the gap
    threshold on a chapter, all gaps for that chapter are escalated to
    ``is_structural=True``.

    Args:
        config: Active ``RetroMesterConfig``.

    Returns:
        The ``SegmentKey`` configured as the analysis baseline
        (default: ``"만학도"``).
    """
    return config.baseline_segment


__all__ = ["assign_segments", "baseline_segment"]
