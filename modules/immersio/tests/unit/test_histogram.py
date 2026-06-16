"""Unit tests for compute_score_histogram (T025).

Spec 004 contracts/xlsx_sheets.md §2 — `1_히스토그램` 시트:
    bin_start | bin_end | count | cumulative | cumulative_pct.

10점 단위 default. 결시 제외. boundary case (점수 = bin_end) → 다음 bin 에 속함.
"""

from __future__ import annotations

import immersio.ingest  # noqa: F401  # required-for: io ↔ ingest import order
import pytest
from immersio.analysis.histogram import compute_score_histogram  # noqa: E402
from paideia_shared.schemas import HistogramBin


def test_histogram_simple_distribution() -> None:
    scores = [5.0, 12.0, 15.0, 18.0, 25.0, 32.0, 47.0, 55.0, 67.0, 95.0]
    bins = compute_score_histogram(scores, bin_size=10.0, max_score=100.0)
    assert all(isinstance(b, HistogramBin) for b in bins)
    counts = {(b.bin_start, b.bin_end): b.count for b in bins}
    assert counts[(0.0, 10.0)] == 1  # 5
    assert counts[(10.0, 20.0)] == 3  # 12, 15, 18
    assert counts[(20.0, 30.0)] == 1  # 25
    assert counts[(30.0, 40.0)] == 1  # 32
    assert counts[(40.0, 50.0)] == 1  # 47
    assert counts[(50.0, 60.0)] == 1  # 55
    assert counts[(60.0, 70.0)] == 1  # 67
    assert counts[(70.0, 80.0)] == 0
    assert counts[(80.0, 90.0)] == 0
    assert counts[(90.0, 100.0)] == 1  # 95


def test_histogram_boundary_score_goes_to_next_bin() -> None:
    """A score equal to bin_end must fall into the *next* bin (half-open [start, end))."""
    scores = [10.0, 20.0]
    bins = compute_score_histogram(scores, bin_size=10.0, max_score=30.0)
    counts = {(b.bin_start, b.bin_end): b.count for b in bins}
    assert counts[(10.0, 20.0)] == 1  # 10 here
    assert counts[(20.0, 30.0)] == 1  # 20 here, not (10, 20)


def test_histogram_top_score_clamped_into_last_bin() -> None:
    """A perfect score equal to max_score is included in the last [n*step, max_score] bin."""
    scores = [100.0]
    bins = compute_score_histogram(scores, bin_size=10.0, max_score=100.0)
    last = bins[-1]
    assert last.bin_start == 90.0
    assert last.bin_end == 100.0
    assert last.count == 1


def test_histogram_cumulative_and_pct_monotonic() -> None:
    scores = [5.0, 15.0, 25.0, 35.0, 45.0, 55.0, 65.0, 75.0, 85.0, 95.0]
    bins = compute_score_histogram(scores, bin_size=10.0, max_score=100.0)
    cumulatives = [b.cumulative for b in bins]
    pcts = [b.cumulative_pct for b in bins]
    assert cumulatives == sorted(cumulatives)
    assert pcts == sorted(pcts)
    assert bins[-1].cumulative == len(scores)
    assert bins[-1].cumulative_pct == pytest.approx(100.0)


def test_histogram_excludes_none_and_nan() -> None:
    """결시 학생은 score 가 None — 분모에서 제외 (research §R-04)."""
    import math

    scores = [10.0, 20.0, None, math.nan, 30.0]  # type: ignore[list-item]
    bins = compute_score_histogram(scores, bin_size=10.0, max_score=40.0)  # type: ignore[arg-type]
    total = sum(b.count for b in bins)
    assert total == 3


def test_histogram_invalid_bin_size_rejected() -> None:
    with pytest.raises(ValueError, match=r"bin_size must be > 0"):
        compute_score_histogram([10.0], bin_size=0.0, max_score=100.0)


def test_histogram_max_score_must_be_positive() -> None:
    with pytest.raises(ValueError, match=r"max_score must be > 0"):
        compute_score_histogram([10.0], bin_size=10.0, max_score=0.0)


def test_histogram_empty_scores_produces_zero_count_bins() -> None:
    bins = compute_score_histogram([], bin_size=10.0, max_score=30.0)
    assert len(bins) == 3
    assert all(b.count == 0 for b in bins)
    assert all(b.cumulative == 0 for b in bins)
    assert all(b.cumulative_pct == 0.0 for b in bins)
