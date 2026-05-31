"""T024 — Blueprint solver: total_items → chapter-even slot list.

Deterministic greedy allocation:
1. Distribute total_items evenly across chapters (max diff ≤ 1).
2. Assign sources (textbook / formative / quiz) to slots respecting source_mix counts.
3. Assign difficulty labels so the whole-exam distribution approximates
   difficulty_targets (45/35/20 default).

No ILP, no external dependencies — pure Python.

Usage::

    from examen.plan.blueprint import solve, Slot

    slots = solve(blueprint, curriculum_map)
    # slots: list[Slot]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from paideia_shared.schemas import CurriculumMap, ExamenBlueprint

# ---------------------------------------------------------------------------
# Slot dataclass
# ---------------------------------------------------------------------------

SourceLabel = Literal["textbook", "formative", "quiz"]
DifficultyLabel = Literal["1_쉬움", "2_보통", "3_어려움"]


@dataclass(frozen=True)
class Slot:
    """One planned exam slot before LLM generation.

    Attributes:
        slot_id: Deterministic identifier (e.g. ``"slot-001"``).
        chapter: Full chapter title string.
        chapter_no: Integer chapter number.
        source: Origin of the question (``"textbook"``, ``"formative"``, ``"quiz"``).
        difficulty: Assigned difficulty label.
        section: Optional target section within the chapter.
        question_type: Optional target question type.
    """

    slot_id: str
    chapter: str
    chapter_no: int
    source: SourceLabel
    difficulty: DifficultyLabel
    section: str | None = None
    question_type: str | None = None


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

# 난이도 라벨 매핑
_DIFFICULTY_MAP: dict[str, DifficultyLabel] = {
    "easy": "1_쉬움",
    "medium": "2_보통",
    "hard": "3_어려움",
}

# 출처 정렬 순서 (소스 믹스 반복 가능 순서)
_SOURCE_ORDER: list[SourceLabel] = ["formative", "quiz", "textbook"]


def _even_distribute(total: int, n_buckets: int) -> list[int]:
    """Distribute *total* integers into *n_buckets* with max diff ≤ 1.

    Returns a list of length ``n_buckets`` where each element is either
    ``total // n_buckets`` or ``total // n_buckets + 1``.
    Larger buckets come first (deterministic: remainder filled left-to-right).

    Args:
        total: Total number of items to distribute.
        n_buckets: Number of buckets.

    Returns:
        List of non-negative integers summing to ``total``.
    """
    if n_buckets == 0:
        return []
    base = total // n_buckets
    remainder = total % n_buckets
    # remainder 개의 버킷이 base+1, 나머지는 base
    return [base + (1 if i < remainder else 0) for i in range(n_buckets)]


def _difficulty_sequence(n: int, targets: dict[str, float]) -> list[DifficultyLabel]:
    """Generate a length-*n* difficulty label sequence matching *targets*.

    Uses round() to allocate integer counts, then fills the sequence in a
    round-robin pattern (easy, medium, hard repeating) so difficulty is
    spread evenly across the slot list rather than clumped at one end.

    Args:
        n: Total number of slots.
        targets: Dict with keys ``"easy"``, ``"medium"``, ``"hard"`` (floats
            summing to ~1.0).

    Returns:
        List of ``DifficultyLabel`` of length exactly *n*.
    """
    # integer 할당: round() → 합산이 n 이 되도록 최대 편차가 가장 큰 것 보정
    easy_n = round(targets.get("easy", 0.45) * n)
    medium_n = round(targets.get("medium", 0.35) * n)
    hard_n = n - easy_n - medium_n
    # hard_n 음수 방지 (극단적 타겟 값)
    if hard_n < 0:
        # easy 에서 보정
        easy_n += hard_n
        hard_n = 0

    # 인터리브: 슬롯 위치 전반에 걸쳐 난이도를 고르게 분산
    # 방법: easy, medium, hard 를 번갈아 배치 (round-robin)
    interleaved: list[DifficultyLabel] = []
    pools: list[list[DifficultyLabel]] = [
        ["1_쉬움"] * easy_n,
        ["2_보통"] * medium_n,
        ["3_어려움"] * hard_n,
    ]
    while sum(len(p) for p in pools) > 0:
        for pool in pools:
            if pool:
                interleaved.append(pool.pop(0))

    return interleaved


def solve(
    blueprint: ExamenBlueprint,
    curriculum_map: CurriculumMap,
) -> list[Slot]:
    """Solve the blueprint: return a chapter-even list of Slots.

    Allocation procedure:
    1. Identify the chapters from ``blueprint.chapters`` and look up their
       ``chapter_no`` from ``curriculum_map``.
    2. Distribute ``blueprint.total_items`` evenly across chapters (max diff ≤ 1).
    3. Assign sources to slots in the order: formative → quiz → textbook (so
       that formative and quiz slots are anchored to specific chapters via
       curriculum_map and the remaining are filled with textbook).
    4. Assign difficulty labels globally (whole-exam distribution) via round-robin
       interleaving so individual chapters are NOT forced to any particular
       difficulty distribution.

    If a chapter in ``blueprint.chapters`` has no matching entry in
    ``curriculum_map``, its ``chapter_no`` defaults to 0 and a sentinel
    ``section=None`` is used (no crash — the quality report surfaces mismatches).

    Args:
        blueprint: Validated exam specification.
        curriculum_map: Week→chapter→section mapping (for chapter_no lookup).

    Returns:
        Deterministic list of :class:`Slot` objects, one per planned exam item.
    """
    # ----------------------------------------------------------------
    # Step 1: build chapter→chapter_no lookup from curriculum_map
    # ----------------------------------------------------------------
    ch_to_no: dict[str, int] = {}
    for entry in curriculum_map.entries:
        # 중복 장은 마지막 entry 를 사용 (동일 chapter_no 를 기대)
        ch_to_no[entry.chapter] = entry.chapter_no

    chapters = list(blueprint.chapters)
    n_chapters = len(chapters)
    if n_chapters == 0:
        return []

    # ----------------------------------------------------------------
    # Step 2: chapter-even distribution
    # ----------------------------------------------------------------
    counts_per_chapter = _even_distribute(blueprint.total_items, n_chapters)
    # chapter → slot count
    chapter_slot_counts: dict[str, int] = dict(
        zip(chapters, counts_per_chapter, strict=True)
    )

    # ----------------------------------------------------------------
    # Step 3: source assignment
    # Expand source_mix into a flat list of sources (stable order)
    # ----------------------------------------------------------------
    source_list: list[SourceLabel] = []
    for src in _SOURCE_ORDER:
        count = blueprint.source_mix.get(src, 0)
        source_list.extend([src] * count)  # type: ignore[arg-type]

    # ----------------------------------------------------------------
    # Step 4: difficulty sequence (whole-exam, interleaved)
    # ----------------------------------------------------------------
    diff_seq = _difficulty_sequence(blueprint.total_items, blueprint.difficulty_targets)

    # ----------------------------------------------------------------
    # Step 5: build slots (chapter-major order, sources interleaved per chapter)
    # ----------------------------------------------------------------
    # We interleave sources within each chapter proportionally.
    # Strategy:
    #   a. For each chapter, determine how many slots of each source type it gets.
    #      We distribute each source's total count chapter-evenly, then use those
    #      per-chapter sub-counts.
    #   b. Combine per-chapter sources in SOURCE_ORDER order.

    # Per-source chapter-even distribution
    per_source_per_chapter: dict[str, list[int]] = {}
    for src in _SOURCE_ORDER:
        total_src = blueprint.source_mix.get(src, 0)
        per_source_per_chapter[src] = _even_distribute(total_src, n_chapters)

    # Build slot list
    slots: list[Slot] = []
    slot_counter = 0  # global index for difficulty and slot_id

    for ch_idx, chapter in enumerate(chapters):
        ch_no = ch_to_no.get(chapter, 0)
        ch_total = chapter_slot_counts[chapter]

        # 챕터별 출처 목록 조립
        ch_sources: list[SourceLabel] = []
        for src in _SOURCE_ORDER:
            src_count_for_ch = per_source_per_chapter[src][ch_idx]
            ch_sources.extend([src] * src_count_for_ch)  # type: ignore[arg-type]

        # Sanity: 챕터별 총 슬롯이 ch_total 과 맞지 않을 때 textbook 으로 보충/절삭
        # (floating-point round 오차 처리)
        while len(ch_sources) < ch_total:
            ch_sources.append("textbook")
        ch_sources = ch_sources[:ch_total]

        # Slot 생성
        for _local_idx, src in enumerate(ch_sources):
            slot_counter += 1
            slot_id = f"slot-{slot_counter:03d}"
            difficulty = diff_seq[slot_counter - 1]
            slots.append(
                Slot(
                    slot_id=slot_id,
                    chapter=chapter,
                    chapter_no=ch_no,
                    source=src,
                    difficulty=difficulty,
                    section=None,
                )
            )

    return slots


__all__ = ["Slot", "solve"]
