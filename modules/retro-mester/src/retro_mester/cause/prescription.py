"""Cause refinement and prescription catalogue for US2 (T033).

Two public functions:

``prescription_for(cause, segment) -> str``
    Catalogue lookup: returns a human-readable Korean prescription string
    differentiated by segment (SC-003).  학령기 prescriptions lean toward
    foundational bridging and step-wise scaffolding; 만학도 prescriptions
    lean toward knowledge restructuring and pacing.

``refine_cause(gap, rows, items, config) -> (CauseLabel, dict)``
    Enriches the US1 cause label with baseline-comparison evidence.
    Flips cause to ``"내용난이도"`` when:
    - The baseline segment's mean correct rate on the chapter is ALSO
      below ``config.gap_threshold`` (same-chapter structural signal), AND
    - At least one item for the chapter has ``expected_difficulty == "어려움"``.

Prescription Catalogue
----------------------
학령기:
  기초구멍  → "1주차 기초 다리 선제 배치"
             (Pre-unit foundational bridge: identify prerequisite gaps
              before instruction; front-load bridging exercises in week 1.)
  내용난이도 → "난이도 계단식 분해"
             (Ladder decomposition: break complex content into sequential
              micro-steps; model each sub-step explicitly.)
  미상      → "수업 관찰 후 재진단"
             (Default: re-diagnose after classroom observation.)

만학도:
  기초구멍  → "단편지식 재구조화 스캐폴딩"
             (Restructuring scaffold: reconnect fragmented prior knowledge
              to new concepts; use concept-mapping and worked examples.)
  내용난이도 → "핵심 개념 반복·속도 배려"
             (Core-concept repetition with pacing: repeated spaced exposure
              to key concepts; reduce cognitive load per session.)
  미상      → "개별 면담 후 재진단"
             (Default: re-diagnose after individual interview.)
"""

from __future__ import annotations

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    ItemStatistics,
    RetroMesterConfig,
    UnitGap,
)
from paideia_shared.schemas.retro_common import CauseLabel

# ---------------------------------------------------------------------------
# Prescription catalogue
# ---------------------------------------------------------------------------

# Keys: (CauseLabel, SegmentKey)
_CATALOGUE: dict[tuple[str, str], str] = {
    # 학령기 — foundational bridging, explicit step-wise scaffolding
    ("기초구멍", "학령기"): "1주차 기초 다리 선제 배치",
    ("내용난이도", "학령기"): "난이도 계단식 분해",
    ("미상", "학령기"): "수업 관찰 후 재진단",
    # 만학도 — knowledge restructuring, pacing/repetition
    ("기초구멍", "만학도"): "단편지식 재구조화 스캐폴딩",
    ("내용난이도", "만학도"): "핵심 개념 반복·속도 배려",
    ("미상", "만학도"): "개별 면담 후 재진단",
}

# Catch-all fallback for any cause not in catalogue (e.g. US1 edge labels).
_DEFAULT_PRESCRIPTION = "담당 교수 협의 후 재진단"


def prescription_for(cause: str, segment: str) -> str:
    """Look up the Korean prescription string for a (cause, segment) pair.

    SC-003: 학령기 and 만학도 always receive different prescription strings
    for the same cause label — this is structurally guaranteed by the
    catalogue having distinct entries per segment.

    Provides a sensible default for any (cause, segment) combination not
    explicitly listed so the pipeline never returns an empty string.

    Args:
        cause: ``CauseLabel`` string (e.g. ``"기초구멍"``, ``"내용난이도"``).
        segment: ``SegmentKey`` string (``"학령기"`` or ``"만학도"``).

    Returns:
        Human-readable Korean prescription string.
    """
    return _CATALOGUE.get((cause, segment), _DEFAULT_PRESCRIPTION)


def refine_cause(
    gap: UnitGap,
    rows: list[CombinedAnalysisRow],
    items: list[ItemStatistics],
    config: RetroMesterConfig,
) -> tuple[CauseLabel, dict[str, float]]:
    """Refine a US1 cause label with baseline-segment comparison (US2, T033).

    Upgrade rule (applied only once, in priority order):
    1. If ``baseline_segment`` mean correct rate on ``gap.chapter`` is ALSO
       strictly below ``config.gap_threshold`` AND at least one item for the
       chapter has ``expected_difficulty == "어려움"`` → return ``"내용난이도"``.
    2. Otherwise → return the existing ``gap.cause`` unchanged.

    Returned signals always include ``baseline_mean_rate`` so callers can
    trace the evidence that drove (or didn't drive) the upgrade.

    Args:
        gap: The ``UnitGap`` containing the US1 cause label.
        rows: All ``CombinedAnalysisRow`` records for the run.
        items: Full ``ItemStatistics`` list; filtered to ``gap.chapter`` here.
        config: Active ``RetroMesterConfig``; provides ``baseline_segment``
            and ``gap_threshold``.

    Returns:
        A ``(cause_label, signals)`` tuple where ``signals`` includes:
        - ``baseline_mean_rate``: baseline segment mean for this chapter
          (0.0 if no data).
        - ``hard_item_present``: 1.0 if any item has ``expected_difficulty``
          == ``"어려움"``, else 0.0.
    """
    chapter = gap.chapter
    baseline_seg = config.baseline_segment
    threshold = config.gap_threshold

    # Compute baseline segment mean rate for this chapter.
    baseline_rates = [
        row.chapter_correct_rates[chapter]
        for row in rows
        if config.group_roster.get(row.student_id) == baseline_seg
        and chapter in row.chapter_correct_rates
    ]
    baseline_mean_rate = sum(baseline_rates) / len(baseline_rates) if baseline_rates else 0.0

    # Check for hard items on this chapter.
    chapter_items = [it for it in items if it.chapter == chapter]
    hard_item_present = any(it.expected_difficulty == "어려움" for it in chapter_items)

    signals: dict[str, float] = {
        "baseline_mean_rate": baseline_mean_rate,
        "hard_item_present": 1.0 if hard_item_present else 0.0,
    }

    # Upgrade rule: baseline also low + hard items → 내용난이도.
    if (
        baseline_rates  # at least one baseline student has data
        and baseline_mean_rate < threshold
        and hard_item_present
    ):
        return "내용난이도", signals

    # Keep the US1 cause otherwise.
    return gap.cause, signals


__all__ = ["prescription_for", "refine_cause"]
