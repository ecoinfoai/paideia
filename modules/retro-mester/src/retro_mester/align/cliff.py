"""T044 — Cognitive-cliff detection per chapter (US4).

Cliff rule (authoritative):
  For each chapter, the '지식축적' item_type rate is used as the anchor.
  Any other item_type whose cohort rate is BELOW
  (지식축적_rate - cognitive_cliff_drop) is considered "falling off a cliff."
  Strict less-than: equality does NOT trigger a cliff.

  If a chapter has no '지식축적' items, no cliff is detected for that chapter
  (no anchor to compare against).

cohort rates are computed as the mean correct_rate across all ItemStatistics
rows for a given (chapter, item_type) pair.
"""

from __future__ import annotations

from collections import defaultdict

from paideia_shared.schemas import ItemStatistics, RetroMesterConfig

_KNOWLEDGE_TYPE = "지식축적"


def chapter_item_type_rates(
    items: list[ItemStatistics],
) -> dict[str, dict[str, float]]:
    """Compute cohort mean correct_rate per (chapter, item_type).

    Args:
        items: Full ItemStatistics list for the semester.

    Returns:
        Nested dict ``{chapter: {item_type: mean_correct_rate}}``.
        Empty when ``items`` is empty.
    """
    # Accumulate (sum, count) per (chapter, item_type)
    sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for it in items:
        sums[it.chapter][it.item_type] += it.correct_rate
        counts[it.chapter][it.item_type] += 1

    result: dict[str, dict[str, float]] = {}
    for chapter, type_sums in sums.items():
        result[chapter] = {itype: type_sums[itype] / counts[chapter][itype] for itype in type_sums}
    return result


def detect_cliff(
    items: list[ItemStatistics],
    config: RetroMesterConfig,
) -> dict[str, list[str]]:
    """Detect cognitive-cliff item_types per chapter.

    Cliff rule: for each chapter, compute the '지식축적' rate as anchor.
    Any item_type (other than '지식축적') whose mean correct_rate is
    STRICTLY BELOW (anchor - config.cognitive_cliff_drop) is flagged.

    Chapters without any '지식축적' items produce no cliff entry.

    Args:
        items: Full ItemStatistics list for the semester.
        config: Active RetroMesterConfig; provides ``cognitive_cliff_drop``.

    Returns:
        Dict ``{chapter: [failing_item_types]}``.  Only chapters with at
        least one failing item_type are included.
    """
    rates = chapter_item_type_rates(items)
    drop = config.cognitive_cliff_drop
    cliff: dict[str, list[str]] = {}

    for chapter, type_rates in rates.items():
        anchor = type_rates.get(_KNOWLEDGE_TYPE)
        if anchor is None:
            continue  # no knowledge-level anchor → cannot detect cliff

        threshold = anchor - drop
        failing = [
            itype
            for itype, rate in type_rates.items()
            if itype != _KNOWLEDGE_TYPE and rate < threshold  # strict less-than
        ]
        if failing:
            cliff[chapter] = failing

    return cliff


def dominant_failing_level(
    chapter: str,
    cliff: dict[str, list[str]],
    rates: dict[str, dict[str, float]],
) -> str:
    """Return the item_type with the lowest rate among the failing types.

    Used to select the most severely collapsed cognitive level for a chapter,
    which is written into ChangeRecommendation.target_cognitive_level.

    Args:
        chapter: Chapter label.
        cliff: Output of :func:`detect_cliff`.
        rates: Output of :func:`chapter_item_type_rates` (needed for ordering).

    Returns:
        The item_type string with the lowest mean correct_rate among the
        failing types for ``chapter``.  Returns ``"미상"`` when:
        - ``chapter`` is not in ``cliff``, or
        - the failing list is empty, or
        - rate data is unavailable for the chapter.
    """
    failing = cliff.get(chapter)
    if not failing:
        return "미상"

    chapter_rates = rates.get(chapter, {})
    if not chapter_rates:
        return "미상"

    # Return the failing type with the lowest rate
    return min(failing, key=lambda t: chapter_rates.get(t, float("inf")))


__all__ = ["chapter_item_type_rates", "detect_cliff", "dominant_failing_level"]
