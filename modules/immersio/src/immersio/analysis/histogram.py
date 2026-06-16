"""compute_score_histogram — 1_히스토그램 시트 산출 (T035, FR-007).

Spec 004 contracts/xlsx_sheets.md §2 + research §R-04 (결시 제외).
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
from paideia_shared.schemas import HistogramBin


def _is_valid_score(value: object) -> bool:
    if value is None:
        return False
    return not (isinstance(value, float) and math.isnan(value))


def compute_score_histogram(
    scores: Iterable[float | None],
    *,
    bin_size: float = 10.0,
    max_score: float = 100.0,
) -> list[HistogramBin]:
    """Bucket responder scores into half-open ``[start, end)`` bins.

    The final bin ``[n*step, max_score]`` is *closed* on both sides so a
    perfect score lands in the last bin rather than overflowing.

    Args:
        scores: Per-responder total scores. ``None`` and ``NaN`` are dropped
            (결시 students per research §R-04).
        bin_size: Bin width (default 10.0). Must be > 0.
        max_score: Maximum possible score (default 100.0). Must be > 0.

    Returns:
        ``HistogramBin`` rows in ascending ``bin_start`` order. Cumulative
        count and ``cumulative_pct`` are populated for downstream chart
        anchoring.

    Raises:
        ValueError: When ``bin_size <= 0`` or ``max_score <= 0``.
    """
    if bin_size <= 0:
        raise ValueError(f"compute_score_histogram: bin_size must be > 0, got {bin_size}")
    if max_score <= 0:
        raise ValueError(f"compute_score_histogram: max_score must be > 0, got {max_score}")

    valid_scores = np.array(
        [float(s) for s in scores if _is_valid_score(s)],
        dtype=float,
    )
    n_responders = valid_scores.size

    edges: list[tuple[float, float]] = []
    start = 0.0
    while start < max_score:
        end = min(start + bin_size, max_score)
        edges.append((start, end))
        start = end

    bins: list[HistogramBin] = []
    cumulative = 0
    for idx, (lo, hi) in enumerate(edges):
        is_last = idx == len(edges) - 1
        if is_last:
            mask = (valid_scores >= lo) & (valid_scores <= hi)
        else:
            mask = (valid_scores >= lo) & (valid_scores < hi)
        count = int(mask.sum())
        cumulative += count
        pct = (cumulative / n_responders) * 100.0 if n_responders > 0 else 0.0
        bins.append(
            HistogramBin(
                bin_start=lo,
                bin_end=hi,
                count=count,
                cumulative=cumulative,
                cumulative_pct=pct,
            )
        )
    return bins
