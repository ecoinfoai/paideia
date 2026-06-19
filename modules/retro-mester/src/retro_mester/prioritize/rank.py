"""Gap ranking and recommendation generation (T024, US1).

Converts ``UnitGap`` records into ``ChangeRecommendation`` instances with
priority quadrant assignment, effort lookup, and top-5 coverage marking.

Priority quadrant rules (documented here as the authoritative threshold spec):
  Threshold: impact ``HIGH`` iff ``impact_score >= median(all impact scores)``.
  Threshold: effort  ``HIGH`` iff ``effort_level == "상"`` (상=어려움/hard).
  Quadrant matrix:
    HIGH impact + LOW  effort → "빠른승리"  (quick win)
    HIGH impact + HIGH effort → "큰베팅"    (big bet)
    LOW  impact + LOW  effort → "낮은우선"  (low priority)
    LOW  impact + HIGH effort → "보류"      (defer)

Coverage rules:
  - Sort gaps by impact_score descending.
  - Mark top N as covered (``is_covered=True``, ``rank=1..N``) where
    ``N = min(len(gaps), 5)``.
  - When len(gaps) < 3, all gaps are still covered (no padding).
  - Remaining gaps: ``is_covered=False``, ``rank=None``.
  - 근거부족 (insufficient-evidence) units count as permanently-uncovered in the
    coverage denominator (H1 / FR-002): ``total = len(gaps) + insufficient_count``
    and ``uncovered_count = (len(gaps) - cover_count) + insufficient_count``.
  - ``uncovered_ratio = uncovered_count / total``; ``0.0`` when ``total == 0``.
    With no gaps but ``insufficient_count > 0`` the ratio is ``1.0`` (every
    known unit is uncovered), not ``0.0``.

Provisional US1 defaults (later US overwrite):
  - ``target_cognitive_level``: ``"미상"`` — US4 (T044) maps dominant item_type.
  - ``cluster_vocab``: ``None`` — US2 cluster vocab assignment deferred.
  - ``prescription_key``: ``f"{cause}/{segment}"`` — US2 refines via catalogue.
"""

from __future__ import annotations

import statistics

from paideia_shared.schemas import ChangeRecommendation, RetroMesterConfig, UnitGap
from paideia_shared.schemas.retro_common import EffortLevel, PriorityQuadrant


def _resolve_effort(chapter: str, segment: str, config: RetroMesterConfig) -> EffortLevel:
    """Look up effort level for a chapter/segment pair with fallback to '중'.

    Checks ``config.effort_ratings`` for an exact chapter key first, then
    a composite ``"{chapter}|{segment}"`` key.  Defaults to ``"중"`` if neither
    is present.

    Args:
        chapter: Chapter label (e.g. ``"8장 호흡계통"``).
        segment: Segment key (``"학령기"`` or ``"만학도"``).
        config: Active ``RetroMesterConfig``.

    Returns:
        Resolved ``EffortLevel`` value.
    """
    composite_key = f"{chapter}|{segment}"
    effort = config.effort_ratings.get(chapter) or config.effort_ratings.get(composite_key) or "중"
    return effort  # type: ignore[return-value]


def _assign_quadrant(
    impact_score: float,
    median_impact: float,
    effort_level: EffortLevel,
) -> PriorityQuadrant:
    """Assign the 2×2 priority quadrant for a recommendation.

    Impact threshold: ``impact_score >= median_impact`` → HIGH impact.
    Effort threshold: ``effort_level == "상"`` → HIGH effort.

    Args:
        impact_score: Gap's impact score (``n_below * weight``).
        median_impact: Median impact score across all gaps (split point).
        effort_level: Resolved effort level for the chapter.

    Returns:
        One of the four ``PriorityQuadrant`` literals.
    """
    high_impact = impact_score >= median_impact
    high_effort = effort_level == "상"

    if high_impact and not high_effort:
        return "빠른승리"
    if high_impact and high_effort:
        return "큰베팅"
    if not high_impact and not high_effort:
        return "낮은우선"
    return "보류"  # low impact, high effort


def rank_changes(
    gaps: list[UnitGap],
    config: RetroMesterConfig,
    *,
    insufficient_count: int = 0,
) -> tuple[list[ChangeRecommendation], float]:
    """Convert detected gaps to ranked ``ChangeRecommendation`` instances.

    Sorts all gaps by ``impact_score`` descending and marks the top
    ``min(len(gaps), 5)`` as covered (``is_covered=True``, ``rank=1..N``).
    All remaining gaps are marked uncovered.

    근거부족 (insufficient-evidence) units count as permanently-uncovered in the
    coverage denominator (H1 / FR-002): the reported ``uncovered_ratio`` is
    computed over ``len(gaps) + insufficient_count``, so chapters with zero
    cohort evidence honestly lower the coverage.

    Provisional fields set here (to be overwritten by later US):
    - ``target_cognitive_level = "미상"`` (US4 wires dominant item_type)
    - ``cluster_vocab = None`` (US2 wires cluster vocabulary)
    - ``prescription_key = f"{cause}/{segment}"`` (US2 wires catalogue lookup)

    Args:
        gaps: List of ``UnitGap`` instances from ``detect_gaps``.
        config: Active ``RetroMesterConfig``; provides effort_ratings.
        insufficient_count: Number of ``InsufficientEvidenceUnit`` records for
            this run; added to the denominator as permanently-uncovered units.

    Returns:
        A two-tuple ``(recommendations, uncovered_ratio)`` where:
        - ``recommendations``: all gaps as ``ChangeRecommendation`` instances
          (covered + uncovered), in descending impact_score order.
        - ``uncovered_ratio``: fraction of all known units (gaps + insufficient)
          not covered by any recommendation; ``0.0`` when the denominator is
          ``0``, and ``1.0`` when there are no gaps but ``insufficient_count > 0``.
    """
    if not gaps:
        total = insufficient_count
        ratio = (insufficient_count / total) if total > 0 else 0.0
        return [], ratio

    # Sort descending by impact_score; stable sort preserves insertion order for ties.
    sorted_gaps = sorted(gaps, key=lambda g: g.impact_score, reverse=True)

    cover_count = min(len(sorted_gaps), 5)
    total = len(sorted_gaps) + insufficient_count

    # Median impact for quadrant threshold.
    median_impact = statistics.median(g.impact_score for g in sorted_gaps)

    recs: list[ChangeRecommendation] = []
    for idx, gap in enumerate(sorted_gaps):
        is_covered = idx < cover_count
        rank = idx + 1 if is_covered else None

        effort_level = _resolve_effort(gap.chapter, gap.segment, config)
        quadrant = _assign_quadrant(gap.impact_score, median_impact, effort_level)

        recs.append(
            ChangeRecommendation(
                semester=gap.semester,
                course_slug=gap.course_slug,
                rank=rank,
                chapter=gap.chapter,
                # US4: dominant failing item_type — provisional default
                target_cognitive_level="미상",
                segment=gap.segment,
                cause_hypothesis=gap.cause,
                covered_n=gap.n_below,
                covered_pct_segment=gap.pct_segment,
                covered_pct_cohort=gap.pct_cohort,
                unit_importance=gap.unit_importance,
                weight=gap.weight,
                impact_score=gap.impact_score,
                effort_level=effort_level,
                priority_quadrant=quadrant,
                # US2: prescription catalogue refinement — provisional key
                prescription_key=f"{gap.cause}/{gap.segment}",
                # US2: cluster vocabulary label — provisional default
                cluster_vocab=None,
                validity=gap.validity,
                is_covered=is_covered,
            )
        )

    uncovered_count = (len(sorted_gaps) - cover_count) + insufficient_count
    uncovered_ratio = uncovered_count / total

    return recs, uncovered_ratio


__all__ = ["rank_changes"]
