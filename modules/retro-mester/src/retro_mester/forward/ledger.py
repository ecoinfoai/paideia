"""T038 — Build improvement ledger for forward-contract (US3).

``build_ledger`` converts covered ``ChangeRecommendation`` instances into
``ImprovementLedgerEntry`` records — one actionable commitment per covered gap.

Target uplift rule:
    ``target_value = min(gap_threshold + 0.1, 1.0)``

    A 10-point uplift above the detection threshold is a deliberately modest
    target: it signals meaningful improvement without over-committing.  The
    floor of 1.0 prevents nonsensical targets above the maximum possible rate.

entry_id determinism:
    Computed as the first 16 hex characters of
    ``sha256("{course}.{chapter}.{target_cognitive_level}.{segment}")``.
    The same (chapter, segment, cognitive_level, course) tuple always maps to
    the same entry_id regardless of run time or dict ordering.
"""

from __future__ import annotations

import hashlib

from paideia_shared.schemas import (
    ChangeRecommendation,
    ImprovementLedgerEntry,
    RetroMesterConfig,
    UnitGap,
)


def _make_entry_id(
    course: str,
    chapter: str,
    target_cognitive_level: str,
    segment: str,
) -> str:
    """Return a deterministic 16-hex-char entry ID.

    Stable key: ``"{course}.{chapter}.{target_cognitive_level}.{segment}"``.

    Args:
        course: Course slug.
        chapter: Chapter label.
        target_cognitive_level: Cognitive level from the recommendation.
        segment: Student segment label.

    Returns:
        First 16 hex characters of the SHA-256 hash of the key string.
    """
    key = f"{course}.{chapter}.{target_cognitive_level}.{segment}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def build_ledger(
    covered_recs: list[ChangeRecommendation],
    gaps: list[UnitGap],
    config: RetroMesterConfig,
    *,
    created_for_year: str,
) -> list[ImprovementLedgerEntry]:
    """Convert covered recommendations into improvement ledger entries.

    For each covered recommendation, looks up the matching gap by (chapter,
    segment) to retrieve ``segment_mean_rate`` as the baseline value.
    ``target_value`` is ``min(config.gap_threshold + 0.1, 1.0)``.

    Args:
        covered_recs: Recommendations with ``is_covered=True``.  Pass only
            covered records — uncovered records are skipped defensively.
        gaps: All ``UnitGap`` instances from which baseline values are drawn.
        config: Active ``RetroMesterConfig``; provides ``gap_threshold``,
            ``semester``, and ``course_slug``.
        created_for_year: Academic year this commitment targets (e.g. ``"2027-1"``).

    Returns:
        List of ``ImprovementLedgerEntry`` instances, one per covered
        recommendation.  Order mirrors ``covered_recs``.  Empty list when
        ``covered_recs`` is empty.
    """
    if not covered_recs:
        return []

    # Build gap lookup by (chapter, segment) → segment_mean_rate.
    gap_rate: dict[tuple[str, str], float] = {
        (g.chapter, g.segment): g.segment_mean_rate for g in gaps
    }

    target_value = min(config.gap_threshold + 0.1, 1.0)

    entries: list[ImprovementLedgerEntry] = []
    for rec in covered_recs:
        if not rec.is_covered:
            # Defensive: caller should only pass covered recs.
            continue

        baseline_value = gap_rate.get((rec.chapter, rec.segment), 0.0)

        entry_id = _make_entry_id(
            config.course_slug,
            rec.chapter,
            rec.target_cognitive_level,
            rec.segment,
        )

        entries.append(
            ImprovementLedgerEntry(
                entry_id=entry_id,
                semester=config.semester,
                course_slug=config.course_slug,
                chapter=rec.chapter,
                target_cognitive_level=rec.target_cognitive_level,
                segment=rec.segment,
                metric="단원 정답률",
                baseline_value=baseline_value,
                target_value=target_value,
                cluster_vocab=rec.cluster_vocab,
                measure_at="차년도 기말",
                created_for_year=created_for_year,
            )
        )

    return entries


__all__ = ["build_ledger"]
