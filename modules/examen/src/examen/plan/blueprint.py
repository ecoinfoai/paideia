"""T024 / T036 / T043 — Blueprint solver: total_items → chapter-even slot list.

Deterministic greedy allocation:
1. Distribute total_items evenly across chapters (max diff ≤ 1).
2. Assign sources (textbook / formative / quiz) to slots respecting source_mix counts.
3. Assign difficulty labels so the whole-exam distribution approximates
   difficulty_targets (45/35/20 default).

T036 addition: ``validate_formative_count`` checks that
``blueprint.source_mix['formative'] == len(formative_inventory)`` before the
solver runs.  ``solve`` accepts an optional ``formative_inventory`` parameter
and calls the validator automatically when provided.

T043 addition: ``select_quiz_subset`` deterministically selects ``target``
quiz entries from a larger inventory pool, distributing them chapter-evenly
(max count diff ≤ 1).  ``solve`` accepts an optional ``quiz_inventory``
parameter; when provided the solver attaches ``source_ref`` from the
selected subset to each quiz slot for downstream traceability.

No ILP, no external dependencies — pure Python.

Usage::

    from examen.plan.blueprint import solve, validate_formative_count, Slot, select_quiz_subset

    validate_formative_count(blueprint, formative_inventory)
    slots = solve(
        blueprint, curriculum_map,
        formative_inventory=formative_inventory,
        quiz_inventory=quiz_inventory,
    )
    # slots: list[Slot]
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from paideia_shared.schemas import CurriculumMap, ExamenBlueprint, SourceInventoryEntry

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
        source_ref: Optional source reference for formative/quiz slots (links
            back to the SourceInventoryEntry).
    """

    slot_id: str
    chapter: str
    chapter_no: int
    source: SourceLabel
    difficulty: DifficultyLabel
    section: str | None = None
    question_type: str | None = None
    source_ref: str | None = None


# ---------------------------------------------------------------------------
# Solver helpers
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


# ---------------------------------------------------------------------------
# T043 — Quiz chapter-even subset selection
# ---------------------------------------------------------------------------


def select_quiz_subset(
    inventory: list[SourceInventoryEntry],
    target: int,
    chapters: list[int],
) -> list[SourceInventoryEntry]:
    """Select ``target`` quiz entries from ``inventory`` in a chapter-even, deterministic order.

    Algorithm:
    1. Group inventory by ``chapter_no``.
    2. For each chapter in ``chapters`` order, allocate slots using
       ``_even_distribute(target, len(chapters))`` — so the per-chapter
       allocation differs by at most 1.
    3. Take the first N entries from each chapter group (stable order).
    4. Return the flat list in chapter-major order (deterministic).

    Args:
        inventory: Pool of quiz SourceInventoryEntry objects.
        target: Desired total selection count.
        chapters: Ordered list of chapter_no values that must be represented.

    Returns:
        Deterministic list of ``target`` SourceInventoryEntry objects,
        chapter-even.

    Raises:
        ValueError: If ``inventory`` cannot supply ``target`` items
            chapter-evenly (e.g. a chapter has fewer entries than its
            allocated slot count).
    """
    if not inventory:
        raise ValueError(
            f"select_quiz_subset: quiz inventory is empty — "
            f"cannot select {target} items."
        )
    if target <= 0:
        return []

    # Group by chapter_no, preserving original order within each group
    groups: dict[int, list[SourceInventoryEntry]] = defaultdict(list)
    for entry in inventory:
        ch_no = entry.chapter_no if entry.chapter_no is not None else 0
        groups[ch_no].append(entry)

    # Allocate per-chapter using _even_distribute
    n_chapters = len(chapters)
    per_chapter_counts = _even_distribute(target, n_chapters)

    result: list[SourceInventoryEntry] = []
    for ch_no, alloc in zip(chapters, per_chapter_counts, strict=False):
        available = groups.get(ch_no, [])
        if len(available) < alloc:
            raise ValueError(
                f"select_quiz_subset: chapter {ch_no} needs {alloc} quiz items "
                f"but only {len(available)} available in inventory. "
                "quiz_inventory 가 충분하지 않습니다 — 더 많은 퀴즈 문항을 추가하거나 "
                "target 을 줄이세요."
            )
        result.extend(available[:alloc])

    return result


# ---------------------------------------------------------------------------
# T036 — Formative 전수 슬롯 예약 + source_mix.formative == 대장수 검증
# ---------------------------------------------------------------------------


def validate_formative_count(
    blueprint: ExamenBlueprint,
    formative_inventory: list[SourceInventoryEntry],
) -> None:
    """Validate that blueprint.source_mix['formative'] == len(formative_inventory).

    This is the "formative == 대장수" cross-check from the spec (data-model §1).
    It must be called at ingest/pipeline time when both artefacts are loaded.

    Args:
        blueprint: Validated exam specification.
        formative_inventory: List of SourceInventoryEntry objects with
            source="formative" (the actually-administered items).

    Raises:
        ValueError: If the counts do not match (located error — includes both
            the blueprint value and the inventory size).
    """
    declared = blueprint.source_mix.get("formative", 0)
    actual = len(formative_inventory)
    if declared != actual:
        raise ValueError(
            f"validate_formative_count: blueprint.source_mix['formative'] == {declared} "
            f"but len(formative_inventory) == {actual}. "
            "형성평가 전수 포함 불변식 위반: blueprint 선언 수와 실제 대장 수가 일치해야 합니다. "
            "blueprint.source_mix.formative 또는 formative_inventory 를 수정하세요."
        )


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------


def solve(
    blueprint: ExamenBlueprint,
    curriculum_map: CurriculumMap,
    formative_inventory: list[SourceInventoryEntry] | None = None,
    quiz_inventory: list[SourceInventoryEntry] | None = None,
) -> list[Slot]:
    """Solve the blueprint: return a chapter-even list of Slots.

    Allocation procedure:
    1. If ``formative_inventory`` is provided, validate the count against
       ``blueprint.source_mix['formative']`` (T036 cross-check).
    2. If ``quiz_inventory`` is provided, select ``source_mix['quiz']`` items
       chapter-evenly via ``select_quiz_subset`` (T043).
    3. Identify the chapters from ``blueprint.chapters`` and look up their
       ``chapter_no`` from ``curriculum_map``.
    4. Distribute ``blueprint.total_items`` evenly across chapters (max diff ≤ 1).
    5. Assign sources to slots in the order: formative → quiz → textbook.
    6. Assign difficulty labels globally (whole-exam distribution) via round-robin
       interleaving so individual chapters are NOT forced to any particular
       difficulty distribution.
    7. For quiz slots, attach ``source_ref`` from the selected quiz subset
       (chapter-major order) for downstream traceability.

    If a chapter in ``blueprint.chapters`` has no matching entry in
    ``curriculum_map``, its ``chapter_no`` defaults to 0 and a sentinel
    ``section=None`` is used (no crash — the quality report surfaces mismatches).

    Args:
        blueprint: Validated exam specification.
        curriculum_map: Week→chapter→section mapping (for chapter_no lookup).
        formative_inventory: Optional list of formative SourceInventoryEntry
            objects.  When provided, their count is validated against
            ``blueprint.source_mix['formative']``.
        quiz_inventory: Optional pool of quiz SourceInventoryEntry objects.
            When provided, ``source_mix['quiz']`` items are selected
            chapter-evenly and their ``source_ref`` values are attached to
            quiz slots.

    Returns:
        Deterministic list of :class:`Slot` objects, one per planned exam item.

    Raises:
        ValueError: If ``formative_inventory`` is provided and its count does
            not match ``blueprint.source_mix['formative']``.
        ValueError: If ``quiz_inventory`` is provided but insufficient to
            fill the required quiz slots chapter-evenly.
    """
    # T036: 형성 전수 검증 (인벤토리 제공 시)
    if formative_inventory is not None:
        validate_formative_count(blueprint, formative_inventory)

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
    # T043: quiz subset selection (인벤토리 제공 시)
    # ----------------------------------------------------------------
    # chapter_no 목록 (blueprint 장 순서대로, curriculum_map 에서 조회)
    chapter_nos_ordered = [ch_to_no.get(ch, 0) for ch in chapters]

    # 퀴즈 슬롯 수
    quiz_target = blueprint.source_mix.get("quiz", 0)

    # quiz_inventory 가 제공되면 챕터 균등으로 quiz_target 개 선택
    # 선택된 항목을 chapter-major 순서로 인덱스에 넣어 slot 생성 시 참조
    selected_quiz: list[SourceInventoryEntry] = []
    if quiz_inventory is not None and quiz_target > 0:
        selected_quiz = select_quiz_subset(
            quiz_inventory,
            target=quiz_target,
            chapters=chapter_nos_ordered,
        )
    # quiz_source_ref_iter: chapter-major 순서로 quiz 슬롯에 source_ref 를 할당
    # (solver 도 chapter-major 로 슬롯을 생성하��로 순서가 일치)
    quiz_ref_iter = iter(entry.source_ref for entry in selected_quiz)

    # ----------------------------------------------------------------
    # Step 2: chapter-even distribution
    # ----------------------------------------------------------------
    counts_per_chapter = _even_distribute(blueprint.total_items, n_chapters)
    # chapter → slot count
    chapter_slot_counts: dict[str, int] = dict(
        zip(chapters, counts_per_chapter, strict=True)
    )

    # ----------------------------------------------------------------
    # Step 3: difficulty sequence (whole-exam, interleaved)
    # ----------------------------------------------------------------
    diff_seq = _difficulty_sequence(blueprint.total_items, blueprint.difficulty_targets)

    # ----------------------------------------------------------------
    # Step 4: build slots (chapter-major order, sources interleaved per chapter)
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

    # 형성평가는 전수 포함이므로 슬롯의 장 분포를 챕터-균등으로 강제하지 않고
    # 인벤토리의 실제 장 분포로 맞춘다.  pipeline 은 형성 슬롯(chapter-major)에
    # 인벤토리(장 오름차순)를 위치 기반으로 바인딩하므로, 불균등 인벤토리에서도
    # 슬롯 장 시퀀스가 인벤토리와 일치해야 조용한 오바인딩이 발생하지 않는다.
    if formative_inventory:
        formative_by_chapter = defaultdict(int)
        for entry in formative_inventory:
            if entry.chapter_no is not None:
                formative_by_chapter[entry.chapter_no] += 1
        per_source_per_chapter["formative"] = [
            formative_by_chapter[ch_to_no.get(ch, 0)] for ch in chapters
        ]

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

        # Sanity: 챕터별 총 슬롯이 ch_total 과 맞지 않을 때 textbook 으로 보충/절삭.
        # 출처별·챕터별 정수 배분의 나머지(remainder)가 챕터-균등 배분과 어긋날 수
        # 있어 보정한다 (부동소수점 오차가 아니라 정수 배분 정렬 차이).
        while len(ch_sources) < ch_total:
            ch_sources.append("textbook")
        ch_sources = ch_sources[:ch_total]

        # Slot 생성
        for _local_idx, src in enumerate(ch_sources):
            slot_counter += 1
            slot_id = f"slot-{slot_counter:03d}"
            difficulty = diff_seq[slot_counter - 1]

            # T043: quiz 슬롯에 selected_quiz 의 source_ref 를 순서대로 첨부
            slot_source_ref: str | None = None
            if src == "quiz" and selected_quiz:
                slot_source_ref = next(quiz_ref_iter, None)

            slots.append(
                Slot(
                    slot_id=slot_id,
                    chapter=chapter,
                    chapter_no=ch_no,
                    source=src,
                    difficulty=difficulty,
                    section=None,
                    source_ref=slot_source_ref,
                )
            )

    # 조용한 누락 금지(헌장 III): 챕터별 정수 출처 배분이 source_mix 를
    # 챕터-균등으로 정확히 실현하지 못하는 경우(예: textbook 이 챕터 수보다
    # 적어 per-chapter truncation 이 선언된 quiz/formative 슬롯을 textbook 으로
    # 대체) 실측 출처 수가 선언과 어긋난다. 이를 ⚠️ 리포트로만 흘리지 않고
    # located 실패로 표면화한다(textbook-light blueprint 한정 발생).
    realized: dict[str, int] = dict.fromkeys(_SOURCE_ORDER, 0)
    for slot in slots:
        realized[slot.source] = realized.get(slot.source, 0) + 1
    for src in _SOURCE_ORDER:
        declared = blueprint.source_mix.get(src, 0)
        if realized.get(src, 0) != declared:
            raise ValueError(
                f"solve: source_mix 를 챕터-균등으로 실현할 수 없습니다 — "
                f"출처 '{src}' 선언={declared} 실측={realized.get(src, 0)}. "
                "원인: textbook 슬롯 수가 챕터 수에 비해 적어 일부 챕터의 "
                "정수 배분이 선언된 quiz/formative 슬롯을 밀어냅니다. "
                "blueprint.source_mix(특히 textbook 분)·total_items·chapters 를 "
                "재조정하세요(조용한 누락 금지)."
            )

    return slots


__all__ = ["Slot", "solve", "validate_formative_count", "select_quiz_subset"]
