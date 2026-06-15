"""T049 — Psychometric validity gate: chapter_validity + validity_signals.

Per-chapter aggregate of item statistics → ValidityVerdict.

Verdict rules (applied in this priority order):
1. "판정불가"  — chapter has fewer than 2 items (insufficient data for
                 a psychometric judgement).
2. "문항수선" — chapter is psychometrically problematic:
   (a) LOW-DISC majority: share of items with
       ``discrimination_index < config.low_discrimination_threshold`` >= 0.5, OR
   (b) BAD-DISTRACTOR majority: share of items whose ``distractor_label``
       is in the bad-label set
       {"역변별 의심 — 출제 재검토", "변별 기여 적음 — 차년도 교체 검토"} >= 0.5.
3. "건전"     — otherwise (2+ items, neither (a) nor (b) triggers).

The ``validity_signals`` helper exposes the three numeric ratios so that
callers can trace the decision without re-computing.

Both functions accept a flat list of ItemStatistics records covering
potentially multiple chapters; they group by ``item.chapter`` internally.
"""

from __future__ import annotations

from collections import defaultdict

from paideia_shared.schemas import ItemStatistics, RetroMesterConfig
from paideia_shared.schemas.retro_common import ValidityVerdict

# Bad distractor labels that contribute toward the 문항수선 verdict.
_BAD_DISTRACTOR_LABELS: frozenset[str] = frozenset(
    {
        "역변별 의심 — 출제 재검토",
        "변별 기여 적음 — 차년도 교체 검토",
    }
)

# Minimum item count per chapter for a psychometric verdict.
_MIN_ITEMS = 2

# Majority threshold: a share at or above this triggers 문항수선.
_MAJORITY = 0.5


def validity_signals(
    items: list[ItemStatistics],
    config: RetroMesterConfig,
) -> dict[str, float]:
    """Compute numeric psychometric signals for a flat list of items.

    All items are treated as belonging to the same chapter (the function
    does not group by chapter — callers provide pre-filtered lists).

    Args:
        items: ItemStatistics records for the chapter being analysed.
            An empty list returns all-zero signals.
        config: Provides ``low_discrimination_threshold``.

    Returns:
        Dict with keys:
        - ``"mean_discrimination"``: arithmetic mean of
          ``discrimination_index`` across all items (0.0 when empty).
        - ``"low_disc_share"``: fraction of items with
          ``discrimination_index < config.low_discrimination_threshold``
          (0.0 when empty).
        - ``"bad_distractor_share"``: fraction of items whose
          ``distractor_label`` is in ``_BAD_DISTRACTOR_LABELS``
          (0.0 when empty).
    """
    if not items:
        return {
            "mean_discrimination": 0.0,
            "low_disc_share": 0.0,
            "bad_distractor_share": 0.0,
        }

    threshold = config.low_discrimination_threshold
    n = len(items)

    mean_disc = sum(it.discrimination_index for it in items) / n
    low_disc_count = sum(
        1 for it in items if it.discrimination_index < threshold
    )
    bad_dist_count = sum(
        1 for it in items if it.distractor_label in _BAD_DISTRACTOR_LABELS
    )

    return {
        "mean_discrimination": mean_disc,
        "low_disc_share": low_disc_count / n,
        "bad_distractor_share": bad_dist_count / n,
    }


def chapter_validity(
    items: list[ItemStatistics],
    config: RetroMesterConfig,
) -> dict[str, ValidityVerdict]:
    """Aggregate per-chapter validity verdicts from a list of ItemStatistics.

    Applies the three-tier verdict rule (판정불가 → 문항수선 → 건전) for
    every chapter present in ``items``.

    Verdict rule:
    1. ``< 2`` items in the chapter → ``"판정불가"``
    2. ``low_disc_share >= 0.5`` OR ``bad_distractor_share >= 0.5``
       → ``"문항수선"``
    3. Otherwise → ``"건전"``

    Args:
        items: Flat list of ItemStatistics records (may span multiple chapters).
            Empty list → empty dict.
        config: Active RetroMesterConfig; provides
            ``low_discrimination_threshold``.

    Returns:
        Mapping ``chapter → ValidityVerdict`` for every chapter that
        appears in ``items``.
    """
    # Group items by chapter.
    by_chapter: dict[str, list[ItemStatistics]] = defaultdict(list)
    for it in items:
        by_chapter[it.chapter].append(it)

    result: dict[str, ValidityVerdict] = {}
    for chapter, chapter_items in by_chapter.items():
        if len(chapter_items) < _MIN_ITEMS:
            result[chapter] = "판정불가"
            continue

        sigs = validity_signals(chapter_items, config)
        if (
            sigs["low_disc_share"] >= _MAJORITY
            or sigs["bad_distractor_share"] >= _MAJORITY
        ):
            result[chapter] = "문항수선"
        else:
            result[chapter] = "건전"

    return result


__all__ = ["chapter_validity", "validity_signals"]
