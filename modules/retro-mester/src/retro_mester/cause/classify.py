"""Cause classification for unit gaps (cohort heuristic + prior readiness).

Each chapter × segment gap is assigned one of three ``CauseLabel`` values from
item-level statistics combined with a course-configured prior-readiness signal.

Layering: ``classify_cause`` produces the initial label here; ``prescription.
refine_cause`` runs afterwards in the pipeline and may further upgrade the label
to ``"내용난이도"`` on a structural baseline-also-low + hard-item signal. This
module owns the prior-readiness combination; refine's structural override sits
on top and is not duplicated here.

Prior readiness vocabulary is unconstrained: ``prior_readiness_q5``/``q6`` are
free-form Korean ordinal labels from an external course diagnostic, with no
Literal/enum anywhere in the repo (confirmed by the v0.1.1 vocabulary audit).
Because the labels cannot be safely ordered without guessing semantics, the
low-readiness subgroup is driven solely by ``config.prior_readiness_low_labels``.
When that list is empty there is deliberately no readiness-driven signal — no
quantile split is fabricated — and classification falls back to the item +
baseline heuristic. A course that knows its vocabulary injects the labels via
config without any code change.
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
    """Classify the root cause for a chapter × segment gap.

    Combines item-difficulty statistics with a prior-readiness subgroup signal.
    A segment student counts as "저준비" (low-readiness) when their
    ``prior_readiness_q5`` OR ``prior_readiness_q6`` is in
    ``config.prior_readiness_low_labels``. When that config list is empty the
    low-readiness subgroup is empty (no fabricated ordinal split — the labels
    are unconstrained free-form text) and only the item + baseline heuristic
    applies.

    Rules (applied in priority order):
    1. No items for ``chapter`` → ``"미상"``.
    2. ``hard_share >= 0.5`` → ``"내용난이도"`` (content is genuinely hard;
       ``refine_cause`` reinforces this with a baseline-also-low check).
    3. Low-readiness subgroup is the locus of failure — ``low_readiness_share
       > 0`` AND ``low_readiness_mean_rate < gap_threshold`` while items are not
       broadly hard → ``"기초구멍"``.
    4. ``hard_share < 0.5`` AND ``item_mean_correct_rate < gap_threshold``
       → ``"기초구멍"`` (items are easy but students still fail — basic gaps).
    5. Otherwise → ``"미상"`` (inconclusive signal).

    Args:
        chapter: Chapter label (e.g. ``"8장 호흡계통"``).
        segment: Segment key (``"학령기"`` or ``"만학도"``); selects the students
            whose readiness and chapter rates drive the segment/readiness signals.
        rows: All ``CombinedAnalysisRow`` records for the cohort (both segments).
        items: Full ``ItemStatistics`` list; filtered to ``chapter`` internally.
        config: Active ``RetroMesterConfig``; provides ``gap_threshold``,
            ``baseline_segment``, ``group_roster`` and
            ``prior_readiness_low_labels``.

    Returns:
        A ``(label, signals)`` tuple where ``signals`` always contains:
        - ``hard_share``: share of chapter items with ``expected_difficulty == "어려움"``.
        - ``item_mean_correct_rate``: mean of ``correct_rate`` across chapter items.
        - ``segment_mean_rate``: mean chapter rate across ``segment`` students.
        - ``low_readiness_share``: share of ``segment`` students with chapter data
          that are low-readiness (0.0 when ``low_labels`` is empty or none qualify).
        - ``low_readiness_mean_rate``: mean chapter rate of the low-readiness
          subgroup (0.0 when the subgroup is empty).
        - ``baseline_segment_mean_rate``: mean chapter rate of
          ``config.baseline_segment`` students (0.0 when no data).
    """
    chapter_items = [it for it in items if it.chapter == chapter]

    # --- compute item signals ---
    if chapter_items:
        hard_share = sum(1 for it in chapter_items if it.expected_difficulty == "어려움") / len(
            chapter_items
        )
        item_mean_correct_rate = sum(it.correct_rate for it in chapter_items) / len(chapter_items)
    else:
        hard_share = 0.0
        item_mean_correct_rate = 0.0

    # --- compute segment_mean_rate from rows ---
    segment_rows_with_data = [
        row
        for row in rows
        if config.group_roster.get(row.student_id) == segment
        and chapter in row.chapter_correct_rates
    ]
    segment_rates = [row.chapter_correct_rates[chapter] for row in segment_rows_with_data]
    segment_mean_rate = sum(segment_rates) / len(segment_rates) if segment_rates else 0.0

    # --- compute low-readiness subgroup signals (label-agnostic) ---
    # Empty low_labels → empty subgroup: the free-form ordinal vocabulary is
    # unconstrained, so no quantile split is fabricated.
    low_labels = set(config.prior_readiness_low_labels)
    if low_labels:
        low_readiness_rows = [
            row
            for row in segment_rows_with_data
            if row.prior_readiness_q5 in low_labels or row.prior_readiness_q6 in low_labels
        ]
    else:
        low_readiness_rows = []

    if segment_rows_with_data:
        low_readiness_share = len(low_readiness_rows) / len(segment_rows_with_data)
    else:
        low_readiness_share = 0.0

    if low_readiness_rows:
        low_readiness_mean_rate = sum(
            row.chapter_correct_rates[chapter] for row in low_readiness_rows
        ) / len(low_readiness_rows)
    else:
        low_readiness_mean_rate = 0.0

    # --- compute baseline_segment_mean_rate ---
    baseline_rates = [
        row.chapter_correct_rates[chapter]
        for row in rows
        if config.group_roster.get(row.student_id) == config.baseline_segment
        and chapter in row.chapter_correct_rates
    ]
    baseline_segment_mean_rate = (
        sum(baseline_rates) / len(baseline_rates) if baseline_rates else 0.0
    )

    signals: dict[str, float] = {
        "hard_share": hard_share,
        "item_mean_correct_rate": item_mean_correct_rate,
        "segment_mean_rate": segment_mean_rate,
        "low_readiness_share": low_readiness_share,
        "low_readiness_mean_rate": low_readiness_mean_rate,
        "baseline_segment_mean_rate": baseline_segment_mean_rate,
    }

    # --- rule engine ---
    if not chapter_items:
        return "미상", signals

    if hard_share >= 0.5:
        return "내용난이도", signals

    if low_readiness_share > 0.0 and low_readiness_mean_rate < config.gap_threshold:
        return "기초구멍", signals

    if item_mean_correct_rate < config.gap_threshold:
        return "기초구멍", signals

    return "미상", signals


__all__ = ["classify_cause"]
