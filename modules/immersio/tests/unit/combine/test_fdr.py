"""TDD tests for ``combine.fdr`` BH-FDR helper (T012).

References:
    - Benjamini, Y. & Hochberg, Y. (1995). "Controlling the false discovery
      rate: a practical and powerful approach to multiple testing." JRSS B,
      57(1), 289-300. Example 2 (15 p-values).
    - research.md §R4 — direct scipy.stats.false_discovery_control call.

Reference q-values computed via scipy 1.11+ on the BH-1995 example vector.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from immersio.combine.fdr import bh_fdr_adjust

# BH-1995 Example 2 — 15 raw p-values (sorted ascending in the paper).
_BH1995_P = (
    0.0001,
    0.0004,
    0.0019,
    0.0095,
    0.0201,
    0.0278,
    0.0298,
    0.0344,
    0.0459,
    0.3240,
    0.4262,
    0.5719,
    0.6528,
    0.7590,
    1.000,
)
# Expected BH q-values (scipy reference, ±1e-6 tolerance).
_BH1995_Q_EXPECTED = (
    0.001500,
    0.003000,
    0.009500,
    0.035625,
    0.060300,
    0.063857,
    0.063857,
    0.064500,
    0.076500,
    0.486000,
    0.581182,
    0.714875,
    0.753231,
    0.813214,
    1.000000,
)


def test_bh1995_example_matches_reference() -> None:
    """T012 core: BH-1995 Example 2 → scipy reference ±1e-6."""
    q = bh_fdr_adjust(list(_BH1995_P))
    assert len(q) == len(_BH1995_P)
    for got, expected in zip(q, _BH1995_Q_EXPECTED):
        assert math.isclose(got, expected, abs_tol=1e-6), f"q={got} expected={expected}"


def test_input_order_preserved() -> None:
    """Input order must be preserved (NOT sorted): caller maps q back by index."""
    p_unsorted = [0.5, 0.01, 0.3, 0.001]
    q = bh_fdr_adjust(p_unsorted)
    # p[1]=0.01 and p[3]=0.001 should have the smallest q values; ordering
    # of result reflects input order.
    assert q[1] < q[0]
    assert q[3] < q[0]
    assert q[3] <= q[1]


def test_n_eq_1_returns_p_unchanged() -> None:
    """Single test ⇒ q == p (no correction)."""
    q = bh_fdr_adjust([0.04])
    assert math.isclose(q[0], 0.04, abs_tol=1e-12)


def test_all_zero_p_yields_zero_q() -> None:
    q = bh_fdr_adjust([0.0, 0.0, 0.0])
    assert all(qi == 0.0 for qi in q)


def test_all_one_p_yields_one_q() -> None:
    q = bh_fdr_adjust([1.0, 1.0, 1.0])
    assert all(math.isclose(qi, 1.0, abs_tol=1e-12) for qi in q)


def test_q_clamped_to_unit_interval() -> None:
    """All q-values must be in [0, 1]."""
    q = bh_fdr_adjust(list(_BH1995_P))
    for qi in q:
        assert 0.0 <= qi <= 1.0


def test_invalid_p_above_one_rejected() -> None:
    with pytest.raises(ValueError, match="p-value"):
        bh_fdr_adjust([0.5, 1.5])


def test_invalid_p_below_zero_rejected() -> None:
    with pytest.raises(ValueError, match="p-value"):
        bh_fdr_adjust([-0.01, 0.5])


def test_nan_p_rejected() -> None:
    with pytest.raises(ValueError, match="p-value"):
        bh_fdr_adjust([0.5, float("nan")])


def test_empty_input_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        bh_fdr_adjust([])


def test_numpy_array_input_accepted() -> None:
    q = bh_fdr_adjust(np.array(_BH1995_P))
    assert len(q) == 15
    assert math.isclose(q[0], _BH1995_Q_EXPECTED[0], abs_tol=1e-6)


def test_tied_p_values_stable_sort() -> None:
    """T012 determinism vector 7 — tied p-values must produce stable q output.

    Two p=0.05 with identical inputs in different positions ⇒ identical q
    rank. Repeated invocation byte-identical (no random tie-breaking).
    """
    p = [0.05, 0.01, 0.05, 0.10, 0.001]
    q1 = bh_fdr_adjust(p)
    q2 = bh_fdr_adjust(p)
    assert q1 == q2  # exact equality (no float drift on repeated call)
    # The two tied 0.05 entries (indices 0 and 2) should receive identical q
    assert math.isclose(q1[0], q1[2], abs_tol=1e-12)


def test_returns_list_not_ndarray() -> None:
    """Public contract: returns plain list[float] for JSON/Pydantic friendliness."""
    q = bh_fdr_adjust([0.01, 0.05])
    assert isinstance(q, list)
    assert all(isinstance(qi, float) for qi in q)
