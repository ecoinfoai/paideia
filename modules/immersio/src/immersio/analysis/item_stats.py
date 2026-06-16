"""compute_item_statistics — ItemStatistics row builder (T038, FR-009/010/012).

Aggregates per-item from the responses long-form DataFrame:
- 정답률 / 무응답률 (research §R-04)
- option_distribution (무응답 제외, 합 ≤ 1.0)
- top_distractor_no / rate / is_adjacent (정답 인접 보기 1)
- discrimination_index + point_biserial (optional, total_scores 주어졌을 때)
- distractor_label (룰셋 평가)

ExamItem-side metadata (chapter, week, item_type, ...) 는 ``items`` 인자 (list
of dict) 의 각 row 를 ItemStatistics 의 passthrough 필드로 옮긴다.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
from paideia_shared.schemas import (
    DistractorLabel,
    ItemStatistics,
)

from .discrimination import compute_discrimination
from .distractor_labels import label_distractor_pattern


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def _safe_int_response(value: object) -> int | None:
    if _is_blank(value):
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _is_adjacent(option_a: int, option_b: int) -> bool:
    """Two option numbers are adjacent iff abs(diff) == 1.

    Wrap-around (예: 1 ↔ 5) 미적용 — research §R-07 의 '통상 인접만'.
    """
    return abs(option_a - option_b) == 1


def compute_item_statistics(
    *,
    responses_long: pd.DataFrame,
    items: list[dict],
    semester: str,
    course_slug: str,
    total_scores: dict[str, float] | None = None,
) -> list[ItemStatistics]:
    """Build one ``ItemStatistics`` row per item in ``items``.

    Args:
        responses_long: Long-form ``(student_id, item_no, response)``. The
            ``response`` column is a string of the option number ('1'..'5')
            or blank/None for omits.
        items: List of dicts with ExamItem passthrough fields:
            ``item_no``, ``chapter``, ``week``, ``item_type``,
            ``difficulty_level``, ``expected_difficulty``, ``source``,
            ``correct_answer`` (int 1..5).
        semester: Academic semester ('2026-1') for ItemStatistics.semester.
        course_slug: ASCII slug for ItemStatistics.course_slug.
        total_scores: Optional ``{student_id: total_score}`` for
            discrimination / point-biserial computation. When None, both
            metrics default to ``0.0`` and ``None`` respectively.

    Returns:
        ``list[ItemStatistics]`` in the order of ``items`` (item_no asc
        is the caller's responsibility — items 입력 그대로 sort).

    Raises:
        ValueError: When responses_long is empty or items list is empty,
            or when an item lacks a required passthrough field.
    """
    if responses_long.empty:
        raise ValueError("compute_item_statistics: responses_long is empty")
    if not items:
        raise ValueError("compute_item_statistics: items list is empty")

    # discrimination 결과 사전 계산 (옵션)
    if total_scores is not None:
        item_responses_for_disc: dict[int, dict[str, int]] = {}
        for item_meta in items:
            item_no = int(item_meta["item_no"])
            correct_answer = int(item_meta["correct_answer"])
            sub = responses_long[responses_long["item_no"] == item_no]
            mapping: dict[str, int] = {}
            for _, row in sub.iterrows():
                resp = _safe_int_response(row["response"])
                sid = str(row["student_id"])
                mapping[sid] = 1 if resp == correct_answer else 0
            item_responses_for_disc[item_no] = mapping
        disc = compute_discrimination(item_responses_for_disc, total_scores, top_pct=0.27)
    else:
        disc = {}

    out: list[ItemStatistics] = []
    for item_meta in items:
        item_no = int(item_meta["item_no"])
        correct_answer = int(item_meta["correct_answer"])
        sub = responses_long[responses_long["item_no"] == item_no]
        n_responders = len(sub)
        if n_responders == 0:
            continue

        responses_int: list[int | None] = [_safe_int_response(v) for v in sub["response"].tolist()]
        n_omit = sum(1 for r in responses_int if r is None)
        n_correct = sum(1 for r in responses_int if r == correct_answer)

        correct_rate = n_correct / n_responders
        omit_rate = n_omit / n_responders

        non_blank = [r for r in responses_int if r is not None]
        option_counts = Counter(non_blank)
        option_distribution: dict[int, float] = {
            opt: count / n_responders for opt, count in option_counts.items()
        }

        wrong_only = [r for r in non_blank if r != correct_answer]
        wrong_counts = Counter(wrong_only)
        if wrong_counts:
            top_distractor_no, top_count = max(wrong_counts.items(), key=lambda kv: (kv[1], -kv[0]))
            top_distractor_rate: float | None = top_count / n_responders
            is_top_distractor_adjacent = _is_adjacent(correct_answer, top_distractor_no)
        else:
            top_distractor_no = None  # type: ignore[assignment]
            top_distractor_rate = None
            is_top_distractor_adjacent = False

        disc_result = disc.get(item_no)
        if disc_result is not None:
            discrimination_index = disc_result.discrimination_index
            point_biserial = disc_result.point_biserial
        else:
            discrimination_index = 0.0
            point_biserial = None

        label: DistractorLabel = label_distractor_pattern(
            correct_rate=correct_rate,
            discrimination_index=discrimination_index,
            omit_rate=omit_rate,
            top_distractor_rate=(top_distractor_rate or 0.0),
            is_top_distractor_adjacent=is_top_distractor_adjacent,
        )

        out.append(
            ItemStatistics(
                item_no=item_no,
                semester=semester,
                course_slug=course_slug,
                chapter=str(item_meta["chapter"]),
                week=item_meta.get("week"),
                item_type=str(item_meta["item_type"]),
                difficulty_level=int(item_meta["difficulty_level"]),
                expected_difficulty=item_meta["expected_difficulty"],
                source=item_meta["source"],
                correct_answer=correct_answer,
                n_responders=n_responders,
                n_correct=n_correct,
                n_omit=n_omit,
                correct_rate=correct_rate,
                omit_rate=omit_rate,
                discrimination_index=discrimination_index,
                point_biserial=point_biserial,
                top_distractor_no=top_distractor_no,
                top_distractor_rate=top_distractor_rate,
                is_top_distractor_adjacent=is_top_distractor_adjacent,
                option_distribution=option_distribution,
                distractor_label=label,
            )
        )
    return out
