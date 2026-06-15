"""T045 — Teaching-assessment alignment builder (US4).

Produces one ``AlignmentFinding`` per chapter, comparing taught weeks,
tested items, and cognitive profile to emit an alignment flag.

Flag rules (authoritative spec):
  Priority (highest first):
  1. 인지수준절벽: chapter appears in the cliff dict (from detect_cliff).
  2. 과소교수-과다평가: tested_share - taught_share > SHARE_MARGIN (0.10),
     meaning the chapter is under-taught but over-represented in the exam.
  3. 과다교수-과소평가: taught_share - tested_share > SHARE_MARGIN (0.10),
     meaning the chapter is over-taught but under-represented in the exam.
  4. 정렬됨: none of the above.

  Where:
    tested_share = tested_items_for_chapter / total_tested_items_across_all_chapters
    taught_share = taught_weeks_for_chapter / total_taught_weeks_across_all_chapters

SHARE_MARGIN = 0.10

``기대-실제괴리`` is reserved for item-difficulty mismatch and is NOT
assigned by this function.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from paideia_shared.schemas import (
    CombinedAnalysisRow,
    ExamenBlueprint,
    ItemStatistics,
    RetroMesterConfig,
)
from paideia_shared.schemas.alignment_finding import AlignmentFinding
from paideia_shared.schemas.curriculum_map import CurriculumMap
from paideia_shared.schemas.retro_common import AlignmentFlag

from retro_mester.align.cliff import chapter_item_type_rates, detect_cliff

_SHARE_MARGIN: float = 0.10


def _build_chapter_universe(
    items: list[ItemStatistics],
    curriculum: CurriculumMap,
    blueprint: ExamenBlueprint,
) -> set[str]:
    """Union of all chapters mentioned in items, curriculum, and blueprint."""
    chapters: set[str] = set()
    for it in items:
        chapters.add(it.chapter)
    for entry in curriculum.entries:
        chapters.add(entry.chapter)
    chapters.update(blueprint.chapters)
    return chapters


def build_alignment(
    items: list[ItemStatistics],
    curriculum: CurriculumMap,
    blueprint: ExamenBlueprint,
    rows: list[CombinedAnalysisRow],
    config: RetroMesterConfig,
) -> list[AlignmentFinding]:
    """Build one AlignmentFinding per chapter in the combined chapter universe.

    Steps per chapter:
    1. Count taught_weeks from CurriculumMap entries.
    2. Count tested_items from ItemStatistics.
    3. Compute learned_rate = cohort mean of chapter_correct_rates[chapter].
    4. Extract cognitive_profile from chapter_item_type_rates.
    5. Compute tested_share and taught_share (fractions of totals).
    6. Assign flag via the priority rules above.

    Note: chapters with zero taught_weeks AND zero tested_items are skipped
    (they carry no meaningful alignment signal).

    Args:
        items: Full ItemStatistics list.
        curriculum: Parsed CurriculumMap.
        blueprint: Parsed ExamenBlueprint (provides chapter universe).
        rows: CombinedAnalysisRow records for cohort rate computation.
        config: Active RetroMesterConfig; provides cognitive_cliff_drop.

    Returns:
        List of AlignmentFinding, one per chapter, in sorted chapter order.
    """
    chapters = _build_chapter_universe(items, curriculum, blueprint)

    # Cliff detection
    cliff = detect_cliff(items, config)

    # Per-chapter item_type rates (cognitive_profile)
    type_rates = chapter_item_type_rates(items)

    # taught_weeks per chapter
    taught_counter: Counter[str] = Counter()
    for entry in curriculum.entries:
        taught_counter[entry.chapter] += 1

    # tested_items per chapter
    tested_counter: Counter[str] = Counter()
    for it in items:
        tested_counter[it.chapter] += 1

    # Totals for share computation
    total_taught = sum(taught_counter.values())
    total_tested = sum(tested_counter.values())

    # Cohort mean correct rate per chapter
    rate_sums: dict[str, float] = defaultdict(float)
    rate_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        for ch, rate in row.chapter_correct_rates.items():
            rate_sums[ch] += rate
            rate_counts[ch] += 1

    findings: list[AlignmentFinding] = []

    for chapter in sorted(chapters):
        taught_weeks = taught_counter.get(chapter, 0)
        tested_items = tested_counter.get(chapter, 0)

        # Skip chapters with no signal at all
        if taught_weeks == 0 and tested_items == 0:
            continue

        n_rates = rate_counts.get(chapter, 0)
        learned_rate = rate_sums[chapter] / n_rates if n_rates > 0 else 0.0
        cognitive_profile = type_rates.get(chapter, {})

        # Compute shares (safe division)
        tested_share = tested_items / total_tested if total_tested > 0 else 0.0
        taught_share = taught_weeks / total_taught if total_taught > 0 else 0.0

        # Assign flag — priority: cliff > under-taught > over-taught > aligned
        flag: AlignmentFlag
        if chapter in cliff:
            flag = "인지수준절벽"
        elif tested_share - taught_share > _SHARE_MARGIN:
            flag = "과소교수-과다평가"
        elif taught_share - tested_share > _SHARE_MARGIN:
            flag = "과다교수-과소평가"
        else:
            flag = "정렬됨"

        findings.append(
            AlignmentFinding(
                semester=config.semester,
                course_slug=config.course_slug,
                chapter=chapter,
                taught_weeks=taught_weeks,
                tested_items=tested_items,
                learned_rate=learned_rate,
                cognitive_profile=cognitive_profile,
                flag=flag,
                interest_gap=None,
                aversion_gap=None,
                note="",
            )
        )

    return findings


__all__ = ["build_alignment"]
