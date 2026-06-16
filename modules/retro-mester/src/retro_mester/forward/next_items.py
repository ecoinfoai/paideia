"""T041 — Next-year diagnostic item proposals (US3).

``propose_next_items`` generates rule-based, deterministic
``NextYearItemProposal`` instances for the next academic year's diagnostic survey.

Rules:
1. For each structural gap chapter (``is_structural=True``), emit a
   ``likert`` self-understanding proposal if not already proposed.
2. Always emit exactly one ``single_select`` proposal for
   ``"생물 최종학습 시기"`` (absent from current diagnostic for all cohorts).

Deduplication is by ``missing_signal`` value.

``write_next_items_md`` writes a Markdown table to disk.
"""

from __future__ import annotations

from pathlib import Path

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    NextYearItemProposal,
    RetroMesterConfig,
    UnitGap,
)

from retro_mester.output.manager import atomic_write_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MISSING_SIGNAL_BIO_LAST_STUDY = "생물 최종학습 시기"
_TARGET_BIO_LAST_STUDY = "사전학습 이력"

_BIO_RATIONALE = (
    "수강생의 최종 생물 학습 시기 정보가 현재 진단에 없어 "
    "학습 준비도 격차의 원인을 특정하기 어렵습니다. "
    "단일 선택형 문항으로 측정 시 집단 분류 정확도가 향상될 수 있습니다."
)


# ---------------------------------------------------------------------------
# Proposal builder
# ---------------------------------------------------------------------------


def propose_next_items(
    gaps: list[UnitGap],
    rows: list[CombinedAnalysisRow],
    config: RetroMesterConfig,
) -> list[NextYearItemProposal]:
    """Generate rule-based next-year diagnostic item proposals.

    Deterministic: output depends only on ``gaps`` and ``config``; ``rows`` is
    accepted for potential future signal checks but is not used in v0.1.0.

    Args:
        gaps: All ``UnitGap`` instances from the current run.
        rows: All ``CombinedAnalysisRow`` records (available for future
            signal-availability checks; unused in v0.1.0).
        config: Active ``RetroMesterConfig``.

    Returns:
        Deduplicated list of ``NextYearItemProposal`` instances.  Order is
        structural-chapter proposals first (sorted by chapter), then the
        permanent ``"생물 최종학습 시기"`` proposal last.
    """
    seen_signals: set[str] = set()
    proposals: list[NextYearItemProposal] = []

    # Rule 1: one likert self-understanding proposal per structural gap chapter.
    structural_chapters = sorted({g.chapter for g in gaps if g.is_structural})
    for chapter in structural_chapters:
        missing_signal = f"{chapter} 자가이해도"
        if missing_signal in seen_signals:
            continue
        seen_signals.add(missing_signal)
        proposals.append(
            NextYearItemProposal(
                semester=config.semester,
                course_slug=config.course_slug,
                missing_signal=missing_signal,
                target_unit_or_axis=chapter,
                proposed_kind="likert",
                rationale=(
                    f"'{chapter}'이 구조적 빈틈으로 판정되었으나 "
                    "현재 진단에 해당 단원에 대한 자가이해도 측정 문항이 없어 "
                    "학습 준비도와 성취 격차의 연관성을 파악할 수 없습니다."
                ),
            )
        )

    # Rule 2: always add the permanent bio-last-study signal.
    if _MISSING_SIGNAL_BIO_LAST_STUDY not in seen_signals:
        seen_signals.add(_MISSING_SIGNAL_BIO_LAST_STUDY)
        proposals.append(
            NextYearItemProposal(
                semester=config.semester,
                course_slug=config.course_slug,
                missing_signal=_MISSING_SIGNAL_BIO_LAST_STUDY,
                target_unit_or_axis=_TARGET_BIO_LAST_STUDY,
                proposed_kind="single_select",
                rationale=_BIO_RATIONALE,
            )
        )

    return proposals


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------

_MD_HEADERS = ("누락 신호", "대상 단원/축", "제안 유형", "근거")


def write_next_items_md(
    path: Path,
    proposals: list[NextYearItemProposal],
) -> None:
    """Write a Markdown table of next-year diagnostic item proposals.

    Args:
        path: Destination ``.md`` file path.  Parent directory must exist.
        proposals: List of ``NextYearItemProposal`` instances to render.
    """
    lines: list[str] = []
    lines.append("# 차년도 진단 문항 제안")
    lines.append("")
    lines.append("| " + " | ".join(_MD_HEADERS) + " |")
    lines.append("| " + " | ".join("---" for _ in _MD_HEADERS) + " |")

    for p in proposals:
        row = (
            p.missing_signal,
            p.target_unit_or_axis,
            p.proposed_kind,
            p.rationale,
        )
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    text = "\n".join(lines)
    atomic_write_text(path, text, encoding="utf-8")


__all__ = ["propose_next_items", "write_next_items_md"]
