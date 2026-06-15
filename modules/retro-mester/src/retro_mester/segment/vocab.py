"""Cluster vocabulary extraction per segment (T034, US2).

``segment_cluster_vocab`` maps each ``SegmentKey`` to the most common
non-null ``cluster_label`` among that segment's students.  The result
populates ``ChangeRecommendation.cluster_vocab``.
"""

from __future__ import annotations

from collections import Counter

from paideia_shared.schemas import CombinedAnalysisRow, RetroMesterConfig
from paideia_shared.schemas.retro_common import SegmentKey
from retro_mester.segment.assign import assign_segments


def segment_cluster_vocab(
    rows: list[CombinedAnalysisRow],
    config: RetroMesterConfig,
) -> dict[SegmentKey, str | None]:
    """Compute the dominant cluster label per segment.

    For each segment present in ``config.group_roster``, collects all
    non-null ``cluster_label`` values from that segment's students, then
    returns the most frequent one.  Returns ``None`` for a segment when
    no student in it has a non-null ``cluster_label``.

    Tie-breaking: ``Counter.most_common(1)`` returns the element with the
    highest count; on exact ties Python's ``Counter`` uses insertion order
    (deterministic for a given input order).

    Students not in ``config.group_roster`` are excluded.

    Args:
        rows: All ``CombinedAnalysisRow`` records for the run.
        config: Active ``RetroMesterConfig`` carrying ``group_roster``.

    Returns:
        Mapping from ``SegmentKey`` to the most common non-null
        ``cluster_label`` in that segment (``None`` when absent).
        Only segments that appear in the data are included as keys.
    """
    if not rows:
        return {}

    buckets, _ = assign_segments(rows, config)

    result: dict[SegmentKey, str | None] = {}
    for segment, segment_rows in buckets.items():
        labels = [
            row.cluster_label
            for row in segment_rows
            if row.cluster_label is not None
        ]
        if labels:
            counter: Counter[str] = Counter(labels)
            result[segment] = counter.most_common(1)[0][0]
        else:
            result[segment] = None

    return result


__all__ = ["segment_cluster_vocab"]
