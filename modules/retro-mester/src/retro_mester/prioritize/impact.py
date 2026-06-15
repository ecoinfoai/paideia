"""Impact coverage helpers for retro-mester (T022, US1).

The main impact calculation (``impact_score = n_below * weight``) lives inside
``detect_gaps`` to keep the UnitGap invariant V2 always satisfied at construction.
This module provides coverage metric helpers reused by ``rank_changes``.
"""

from __future__ import annotations

from paideia_shared.schemas import UnitGap


def coverage_metrics(gap: UnitGap, total_cohort_n: int) -> dict[str, float]:
    """Return coverage fractions for a single gap relative to the whole cohort.

    Args:
        gap: The ``UnitGap`` whose coverage is computed.
        total_cohort_n: Total number of cohort students with valid data for the
            chapter (denominator for cohort-level percentages).

    Returns:
        Dict with keys:
        - ``"covered_n"``: number of students in the segment whose gap this addresses
          (same as ``gap.n_below``).
        - ``"covered_pct_segment"``: fraction of segment students below threshold
          (same as ``gap.pct_segment``).
        - ``"covered_pct_cohort"``: ``gap.n_below / total_cohort_n`` recomputed;
          returns ``0.0`` when ``total_cohort_n == 0`` to avoid division by zero.
    """
    pct_cohort = gap.n_below / total_cohort_n if total_cohort_n > 0 else 0.0
    return {
        "covered_n": float(gap.n_below),
        "covered_pct_segment": gap.pct_segment,
        "covered_pct_cohort": pct_cohort,
    }


__all__ = ["coverage_metrics"]
