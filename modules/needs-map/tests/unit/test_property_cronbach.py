"""Property tests for Cronbach α (T109).

Hypothesis-driven: random Likert int matrices must always produce α ≤ 1.0
and reproducible results across reruns with the same input.
"""

from __future__ import annotations

import math

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st


@given(
    n_responders=st.integers(min_value=10, max_value=200),
    k_items=st.integers(min_value=3, max_value=8),
    seed=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_alpha_bounded_above_by_one(n_responders: int, k_items: int, seed: int) -> None:
    from needs_map.reliability.cronbach import cronbach_alpha

    rng = np.random.default_rng(seed)
    matrix = rng.integers(low=1, high=8, size=(n_responders, k_items)).astype(float)
    alpha = cronbach_alpha(matrix)
    if alpha is None or math.isnan(alpha):
        return
    assert alpha <= 1.0 + 1e-9


@given(
    n_responders=st.integers(min_value=10, max_value=100),
    k_items=st.integers(min_value=3, max_value=6),
    seed=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_alpha_reproducible(n_responders: int, k_items: int, seed: int) -> None:
    """Same input → same α (no hidden randomness in cronbach_alpha)."""
    from needs_map.reliability.cronbach import cronbach_alpha

    rng = np.random.default_rng(seed)
    matrix = rng.integers(low=1, high=8, size=(n_responders, k_items)).astype(float)
    a = cronbach_alpha(matrix.copy())
    b = cronbach_alpha(matrix.copy())
    if a is None or math.isnan(a):
        assert b is None or math.isnan(b)
    else:
        assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
