"""compute_discrimination — 27% top/bottom + point-biserial (T037, FR-008/011).

Spec 004 research §R-03:
- n_27 = round(n * 0.27, half-to-even)
- 총점 boundary 와 동점인 학생은 모두 포함 → 분모 가변
- D = top_correct_rate - bottom_correct_rate ∈ [-1, 1]
- point-biserial: stat_tests.point_biserial 호출 (NaN/상수 → None)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .stat_tests import point_biserial


@dataclass(frozen=True)
class DiscriminationResult:
    """One row per item — discrimination metrics from the 27% method."""

    item_no: int
    discrimination_index: float
    """top_rate − bottom_rate ∈ [-1, 1] (research §R-03)."""

    point_biserial: float | None
    """``stats.pointbiserialr`` correlation, ``None`` when undefined."""

    top_n: int
    """학생 수 — boundary 동점자가 포함되어 round(n * top_pct) 보다 클 수 있다."""

    bottom_n: int


def _round_half_to_even(value: float) -> int:
    """Python ``round`` is half-to-even (banker's rounding) by default."""
    return int(round(value))


def compute_discrimination(
    item_responses: dict[int, dict[str, int]],
    total_scores: dict[str, float],
    *,
    top_pct: float = 0.27,
) -> dict[int, DiscriminationResult]:
    """Compute the 27%-rule discrimination index for each item.

    Args:
        item_responses: ``{item_no: {student_id: 0_or_1}}``. Only students
            present here are scored for that item.
        total_scores: ``{student_id: total_score}``. Determines the
            top/bottom split via descending sort.
        top_pct: Cut-off proportion (default 0.27 per research §R-03).
            Must be in (0.0, 0.5).

    Returns:
        ``{item_no: DiscriminationResult}`` for every key in
        ``item_responses``.

    Raises:
        ValueError: When ``top_pct`` is out of (0, 0.5) or ``total_scores``
            is empty.
    """
    if not (0.0 < top_pct < 0.5):
        raise ValueError(
            f"compute_discrimination: top_pct must be in (0.0, 0.5), got {top_pct}"
        )
    if not total_scores:
        raise ValueError("compute_discrimination: total_scores is empty")

    sorted_students = sorted(
        total_scores.items(), key=lambda kv: kv[1], reverse=True
    )
    n = len(sorted_students)
    n_27 = max(1, _round_half_to_even(n * top_pct))

    if n_27 > n:
        raise ValueError(
            f"compute_discrimination: n_27={n_27} exceeds cohort size {n}"
        )

    top_boundary_score = sorted_students[n_27 - 1][1]
    bottom_boundary_score = sorted_students[-n_27][1]

    top_ids: set[str] = {sid for sid, score in sorted_students if score >= top_boundary_score}
    bottom_ids: set[str] = {
        sid for sid, score in sorted_students if score <= bottom_boundary_score
    }

    out: dict[int, DiscriminationResult] = {}
    score_array = np.array(
        [total_scores[sid] for sid, _ in sorted_students], dtype=float
    )
    student_id_to_idx = {sid: idx for idx, (sid, _) in enumerate(sorted_students)}

    for item_no, responses in item_responses.items():
        top_hits = [responses[sid] for sid in top_ids if sid in responses]
        bottom_hits = [responses[sid] for sid in bottom_ids if sid in responses]
        top_n = len(top_hits)
        bottom_n = len(bottom_hits)
        if top_n == 0 or bottom_n == 0:
            d_index = 0.0
        else:
            top_rate = sum(top_hits) / top_n
            bottom_rate = sum(bottom_hits) / bottom_n
            d_index = top_rate - bottom_rate

        binary_array = np.zeros(n, dtype=int)
        score_for_pb = []
        binary_for_pb = []
        for sid, value in responses.items():
            idx = student_id_to_idx.get(sid)
            if idx is None:
                continue
            binary_array[idx] = int(value)
            score_for_pb.append(score_array[idx])
            binary_for_pb.append(int(value))
        if len(binary_for_pb) >= 2:
            r_pb = point_biserial(
                np.array(binary_for_pb, dtype=int),
                np.array(score_for_pb, dtype=float),
            )
        else:
            r_pb = None

        out[item_no] = DiscriminationResult(
            item_no=item_no,
            discrimination_index=float(d_index),
            point_biserial=r_pb,
            top_n=top_n,
            bottom_n=bottom_n,
        )
    return out
