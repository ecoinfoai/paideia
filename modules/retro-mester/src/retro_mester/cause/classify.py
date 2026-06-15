"""Cause classification for unit gaps (T023, US1 cohort heuristic).

US1 assigns one of three CauseLabel values per chapter × segment pair using
only item-level statistics.  US2 (T033) will refine these labels with
baseline-segment comparison and prior_readiness (prior_readiness_q5/q6 are
categorical strings — no numeric mapping here; defer to US2).
"""

from __future__ import annotations

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    ItemStatistics,
    RetroMesterConfig,
)
from paideia_shared.schemas.retro_common import CauseLabel


def classify_cause(
    chapter: str,
    segment: str,
    rows: list[CombinedAnalysisRow],
    items: list[ItemStatistics],
    config: RetroMesterConfig,
) -> tuple[CauseLabel, dict[str, float]]:
    """Classify the root cause for a chapter × segment gap (US1 heuristic).

    US1 uses only item difficulty distribution and item correct rates.
    Prior readiness (``prior_readiness_q5``/``q6``) is categorical text; numeric
    mapping and baseline-segment refinement are deferred to US2 (T033).

    Rules (applied in priority order):
    1. ``hard_share >= 0.5`` → ``"내용난이도"``  (content is genuinely hard)
    2. ``hard_share < 0.5`` AND ``item_mean_correct_rate < gap_threshold``
       → ``"기초구멍"``  (items are easy but students still fail — basic gaps)
    3. Otherwise → ``"미상"``  (no items, or inconclusive signal)

    Args:
        chapter: Chapter label (e.g. ``"8장 호흡계통"``).
        segment: Segment key (``"학령기"`` or ``"만학도"``), used only to compute
            ``segment_mean_rate`` for the signals dict; not used in the rule logic.
        rows: All ``CombinedAnalysisRow`` records for the cohort (both segments).
            Only students in ``config.group_roster`` that belong to ``segment``
            and have a valid entry for ``chapter`` contribute to ``segment_mean_rate``.
        items: Full ``ItemStatistics`` list; filtered to ``chapter`` internally.
        config: Active ``RetroMesterConfig``; ``gap_threshold`` used as the
            threshold for the 기초구멍 rule.

    Returns:
        A ``(label, signals)`` tuple where ``signals`` always contains:
        - ``hard_share``: share of chapter items with ``expected_difficulty == "어려움"``
        - ``item_mean_correct_rate``: mean of ``correct_rate`` across chapter items
        - ``segment_mean_rate``: mean chapter rate across segment students in rows
    """
    chapter_items = [it for it in items if it.chapter == chapter]

    # --- compute item signals ---
    if chapter_items:
        hard_share = sum(
            1 for it in chapter_items if it.expected_difficulty == "어려움"
        ) / len(chapter_items)
        item_mean_correct_rate = sum(it.correct_rate for it in chapter_items) / len(
            chapter_items
        )
    else:
        hard_share = 0.0
        item_mean_correct_rate = 0.0

    # --- compute segment_mean_rate from rows ---
    segment_rates = [
        row.chapter_correct_rates[chapter]
        for row in rows
        if config.group_roster.get(row.student_id) == segment
        and chapter in row.chapter_correct_rates
    ]
    segment_mean_rate = (
        sum(segment_rates) / len(segment_rates) if segment_rates else 0.0
    )

    signals: dict[str, float] = {
        "hard_share": hard_share,
        "item_mean_correct_rate": item_mean_correct_rate,
        "segment_mean_rate": segment_mean_rate,
    }

    # --- rule engine ---
    if not chapter_items:
        return "미상", signals

    if hard_share >= 0.5:
        return "내용난이도", signals

    if item_mean_correct_rate < config.gap_threshold:
        return "기초구멍", signals

    return "미상", signals


__all__ = ["classify_cause"]
