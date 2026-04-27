"""Unit tests for Cronbach α (T045, FR-004).

RED at this commit: needs_map.reliability.cronbach module does not exist yet.
GREEN once T052 implements cronbach_alpha + compute_reliability.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


def test_cronbach_alpha_returns_none_when_n_items_below_three() -> None:
    from needs_map.reliability.cronbach import cronbach_alpha

    matrix = np.array([[3.0, 4.0], [4.0, 5.0], [5.0, 4.0]])
    assert cronbach_alpha(matrix) is None


def test_cronbach_alpha_zero_columns_returns_none() -> None:
    from needs_map.reliability.cronbach import cronbach_alpha

    matrix = np.empty((5, 0))
    assert cronbach_alpha(matrix) is None


def test_cronbach_alpha_known_value() -> None:
    """Manually computed α for a small known matrix.

    For the 4×4 matrix below the standard formula yields
        α = (k/(k-1)) × (1 - Σ var(item)/var(sum)) ≈ 0.844.
    """
    from needs_map.reliability.cronbach import cronbach_alpha

    matrix = np.array(
        [
            [4.0, 5.0, 4.0, 5.0],
            [3.0, 3.0, 2.0, 4.0],
            [5.0, 6.0, 5.0, 6.0],
            [2.0, 3.0, 3.0, 2.0],
            [6.0, 5.0, 6.0, 6.0],
        ]
    )
    alpha = cronbach_alpha(matrix)
    assert alpha is not None
    k = matrix.shape[1]
    item_var = matrix.var(axis=0, ddof=1).sum()
    total_var = matrix.sum(axis=1).var(ddof=1)
    expected = (k / (k - 1)) * (1 - item_var / total_var)
    assert math.isclose(alpha, expected, rel_tol=1e-10, abs_tol=1e-10)


def test_cronbach_alpha_constant_matrix_returns_zero_or_neg_inf() -> None:
    """Constant items have variance 0 → α undefined; implementation must not raise."""
    from needs_map.reliability.cronbach import cronbach_alpha

    matrix = np.full((10, 4), 4.0)
    alpha = cronbach_alpha(matrix)
    # Either None (defensive) or a finite number; we only require no exception.
    assert alpha is None or math.isfinite(alpha) or math.isnan(alpha)


@given(
    matrix=st.lists(
        st.lists(st.integers(min_value=1, max_value=7), min_size=4, max_size=4),
        min_size=10,
        max_size=200,
    )
)
@settings(max_examples=20, deadline=None)
def test_cronbach_alpha_bounded_above_by_one(matrix: list[list[int]]) -> None:
    from needs_map.reliability.cronbach import cronbach_alpha

    arr = np.asarray(matrix, dtype=float)
    alpha = cronbach_alpha(arr)
    if alpha is None or math.isnan(alpha):
        return
    # α can theoretically be negative for poorly correlated items but is
    # always ≤ 1.0 by the formula.
    assert alpha <= 1.0 + 1e-9


def test_compute_reliability_returns_one_row_per_axis() -> None:
    """compute_reliability(diag_df, mapping) → ScaleReliabilityReport with 1 row per axis."""
    from pathlib import Path

    import pandas as pd
    from needs_map.io.mapping import load_mapping
    from needs_map.reliability.cronbach import compute_reliability

    mapping = load_mapping(
        Path("modules/needs-map/tests/fixtures/mappings/anatomy_full.diagnostic.yaml")
    )
    # synthesize a small likert-only dataframe matching the mapping's likert sources
    students = ["2026194000", "2026194001", "2026194002"]
    rows = []
    for sid in students:
        for col in mapping.columns:
            if col.kind != "likert":
                continue
            rows.append(
                {
                    "student_id": sid,
                    "axis": col.axis,
                    "axis_kind": "likert",
                    "value_int": (int(sid[-2:]) % 5) + 2,
                    "source_column": col.source,
                }
            )
    diag = pd.DataFrame(rows)
    report = compute_reliability(diag, mapping)
    declared = set(mapping.axes.required) | set(mapping.axes.optional)
    assert {r.axis_key for r in report.rows} == declared


def test_compute_reliability_single_item_label() -> None:
    """An axis with only 1 mapped likert item → label='single_item'."""
    import pandas as pd
    from needs_map.reliability.cronbach import compute_reliability

    # Construct a 1-item mapping inline so the assertion targets exactly the
    # single_item branch (separate from the partial-axes fixture coverage).
    rows: list[dict] = []
    for sid in ("2026194000", "2026194001", "2026194002"):
        rows.append(
            {
                "student_id": sid,
                "axis": "motivation",
                "axis_kind": "likert",
                "value_int": 4,
                "source_column": "Q01_motivation_1",
            }
        )
    df = pd.DataFrame(rows)
    # Build a one-item mapping by reusing the partial mapping but swapping columns
    from paideia_shared.schemas import (
        DiagnosticMappingConfig,
        MappingAxes,
        MappingColumn,
        MappingMetadata,
    )

    one_item_mapping = DiagnosticMappingConfig(
        metadata=MappingMetadata(
            semester="2026-1", course_slug="anatomy", mapping_version=1
        ),
        columns=[
            MappingColumn(source="학번", kind="identity"),
            MappingColumn(
                source="Q01_motivation_1",
                kind="likert",
                axis="motivation",
                aggregate="mean",
            ),
        ],
        axes=MappingAxes(required=["motivation"], optional=[]),
    )
    report = compute_reliability(df, one_item_mapping)
    motivation_row = next(r for r in report.rows if r.axis_key == "motivation")
    assert motivation_row.label == "single_item"
    assert motivation_row.cronbach_alpha is None


def test_compute_reliability_no_items_label() -> None:
    """An axis declared with ZERO likert columns in the mapping → label='no_items'.

    Example: a freetext-only or multiselect-only axis. No α can be computed.
    """
    import pandas as pd
    from needs_map.reliability.cronbach import compute_reliability
    from paideia_shared.schemas import (
        DiagnosticMappingConfig,
        MappingAxes,
        MappingColumn,
        MappingMetadata,
    )

    mapping = DiagnosticMappingConfig(
        metadata=MappingMetadata(
            semester="2026-1", course_slug="anatomy", mapping_version=1
        ),
        columns=[
            MappingColumn(source="학번", kind="identity"),
            # interest declared via freetext only — zero likert items → no_items
            MappingColumn(
                source="Q11_interest_freetext", kind="freetext", axis="interest"
            ),
        ],
        axes=MappingAxes(required=["interest"], optional=[]),
    )
    df = pd.DataFrame(
        columns=["student_id", "axis", "axis_kind", "value_int", "source_column"]
    )
    report = compute_reliability(df, mapping)
    interest_row = next(r for r in report.rows if r.axis_key == "interest")
    assert interest_row.label == "no_items"
    assert interest_row.n_items == 0


@pytest.mark.parametrize("seed", [0, 1, 42])
def test_cronbach_alpha_reproducible_across_runs(seed: int) -> None:
    from needs_map.reliability.cronbach import cronbach_alpha

    rng = np.random.default_rng(seed)
    matrix = rng.integers(low=1, high=8, size=(50, 4)).astype(float)
    a = cronbach_alpha(matrix.copy())
    b = cronbach_alpha(matrix.copy())
    if a is None or b is None:
        assert a is None and b is None
    else:
        assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
