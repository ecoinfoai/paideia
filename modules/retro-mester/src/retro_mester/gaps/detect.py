"""Gap detection for retro-mester analysis (T021, US1).

Implements ``detect_gaps``: for each chapter × segment combination, computes
whether the segment's mean correct rate falls below ``config.gap_threshold``
and, if so, emits a ``UnitGap`` with pre-computed impact metrics.

Provisional US1 defaults (overwritten by later US):
- ``is_structural``: ``False`` — US2 (T032) adds structural escalation logic.
- ``cohort_failing_item_types``: ``[]`` — US4 computes item-type breakdown.
- ``validity``: ``"판정불가"`` — US5 adds psychometric validity gate.
"""

from __future__ import annotations

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    ItemStatistics,
    RetroMesterConfig,
    UnitGap,
)

from retro_mester.cause.classify import classify_cause
from retro_mester.segment.assign import assign_segments


def detect_gaps(
    rows: list[CombinedAnalysisRow],
    items: list[ItemStatistics],
    config: RetroMesterConfig,
) -> list[UnitGap]:
    """Detect learning gaps per chapter × segment combination.

    For each (chapter, segment) pair found in the data:
    1. Compute ``segment_mean_rate`` and ``evidence_n`` (students with valid data).
    2. Emit a ``UnitGap`` only when ``segment_mean_rate < config.gap_threshold``
       AND ``evidence_n >= 1``.
    3. Compute ``n_below``, ``pct_segment``, ``pct_cohort``, and impact fields.
    4. Assign provisional defaults for US2/US4/US5 fields.

    Students not in ``config.group_roster`` are excluded via ``assign_segments``.

    Threshold: 1차 빈틈 (research R3) — ``segment_mean_rate < gap_threshold`` (strict
    less-than; equality does NOT trigger a gap).

    Args:
        rows: All ``CombinedAnalysisRow`` records for this run.
        items: Full ``ItemStatistics`` list for item-level cause signals.
        config: Active ``RetroMesterConfig``; provides threshold, roster, weights.

    Returns:
        List of ``UnitGap`` instances, one per (chapter, segment) pair where the
        segment mean rate is strictly below ``config.gap_threshold`` and at least
        one student has valid data.  Order is not specified (sorted downstream by
        ``rank_changes``).
    """
    buckets, _ = assign_segments(rows, config)

    # Build chapter universe: union of all chapter keys across all classified rows.
    all_chapters: set[str] = set()
    for segment_rows in buckets.values():
        for row in segment_rows:
            all_chapters.update(row.chapter_correct_rates.keys())

    # Also infer chapters from items (in case items cover chapters with no student data).
    for it in items:
        all_chapters.add(it.chapter)

    threshold = config.gap_threshold
    gaps: list[UnitGap] = []

    for chapter in sorted(all_chapters):  # sorted for deterministic order
        # Total students (all segments) with data for this chapter — cohort denominator.
        cohort_students_with_data = [
            row
            for segment_rows in buckets.values()
            for row in segment_rows
            if chapter in row.chapter_correct_rates
        ]
        total_cohort_n = len(cohort_students_with_data)

        for segment, segment_rows in buckets.items():
            students_with_data = [
                row for row in segment_rows if chapter in row.chapter_correct_rates
            ]
            evidence_n = len(students_with_data)
            if evidence_n < 1:
                continue  # no data for this chapter in this segment → skip

            rates = [row.chapter_correct_rates[chapter] for row in students_with_data]
            segment_mean_rate = sum(rates) / len(rates)

            if segment_mean_rate >= threshold:
                continue  # not a gap (strict threshold)

            n_below = sum(1 for r in rates if r < threshold)
            pct_segment = n_below / evidence_n
            pct_cohort = n_below / total_cohort_n if total_cohort_n > 0 else 0.0

            unit_importance = config.unit_importance.get(chapter, "중")
            weight = config.importance_weights[unit_importance]
            impact_score = n_below * weight

            cause, cause_signals = classify_cause(
                chapter, segment, rows, items, config
            )

            gaps.append(
                UnitGap(
                    semester=config.semester,
                    course_slug=config.course_slug,
                    chapter=chapter,
                    segment=segment,
                    segment_mean_rate=segment_mean_rate,
                    n_below=n_below,
                    pct_segment=pct_segment,
                    pct_cohort=pct_cohort,
                    # US2: structural escalation (T032) — provisional default
                    is_structural=False,
                    # US4: item-type breakdown — provisional default
                    cohort_failing_item_types=[],
                    cause=cause,
                    cause_signals=cause_signals,
                    # US5: validity gate — provisional default
                    validity="판정불가",
                    unit_importance=unit_importance,
                    weight=weight,
                    impact_score=impact_score,
                    evidence_n=evidence_n,
                )
            )

    return gaps


__all__ = ["detect_gaps"]
