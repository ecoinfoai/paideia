"""TDD tests for ``combine.correlation`` (T023, US1).

Verifies the 8-axis × N-exam-metric Pearson matrix:
- per-cell ``scipy.stats.pearsonr`` reference equivalence ±1e-6
- pairwise ``n`` calculation (only rows where both axis_z and metric are
  non-null contribute)
- n<20 ⇒ ``unstable_inference_flag=True`` (FR-005)
- BH-FDR adjusted q-values match ``scipy.stats.false_discovery_control`` on
  the full matrix
- output is ``list[CorrelationCell]`` for direct ingestion into
  xlsx_writer / figures.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from immersio.combine.correlation import compute_correlation_matrix
from paideia_shared.schemas import CorrelationCell
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS
from scipy.stats import false_discovery_control, pearsonr


def _synthetic_df(n: int, seed: int = 0) -> pd.DataFrame:
    """Build a small joiner-shaped DataFrame with the 8 axis_z + total_score
    + chapter_correct_rates dict columns."""
    rng = np.random.default_rng(seed)
    cols: dict[str, object] = {
        "student_id": [f"2026{i:06d}" for i in range(n)],
        "exam_taken": [True] * n,
        "total_score": rng.normal(70, 10, n).tolist(),
        "chapter_correct_rates": [
            {"신경계": float(rng.beta(2, 2)), "근골격계": float(rng.beta(2, 2))} for _ in range(n)
        ],
    }
    for axis in STANDARD_AXIS_KEYS:
        cols[f"{axis}_z"] = rng.normal(0, 1, n).tolist()
    return pd.DataFrame(cols)


# ----------------------------------------------------------------------
# Smoke: shape + return type
# ----------------------------------------------------------------------


def test_returns_list_of_correlation_cell() -> None:
    df = _synthetic_df(n=50)
    cells = compute_correlation_matrix(df)
    assert isinstance(cells, list)
    assert all(isinstance(c, CorrelationCell) for c in cells)


def test_emits_8_axes_times_14_metrics_for_full_synthetic() -> None:
    """8 axes × (total_score + 2 chapter rates) = 24 cells in this synthetic."""
    df = _synthetic_df(n=50)
    cells = compute_correlation_matrix(df)
    assert len(cells) == 8 * 3  # total + 2 chapters


def test_axis_keys_are_standard() -> None:
    df = _synthetic_df(n=50)
    cells = compute_correlation_matrix(df)
    seen_axes = {c.axis_key for c in cells}
    assert seen_axes == set(STANDARD_AXIS_KEYS)


# ----------------------------------------------------------------------
# Reference equivalence — scipy.stats.pearsonr ±1e-6
# ----------------------------------------------------------------------


def test_pearson_r_matches_scipy_reference() -> None:
    df = _synthetic_df(n=80, seed=42)
    cells = compute_correlation_matrix(df)
    cell = next(
        c for c in cells if c.axis_key == "motivation" and c.exam_metric_key == "total_score"
    )
    expected_r, expected_p = pearsonr(df["motivation_z"], df["total_score"])
    assert math.isclose(cell.pearson_r, float(expected_r), abs_tol=1e-6)
    assert math.isclose(cell.raw_p, float(expected_p), abs_tol=1e-6)


def test_pairwise_n_excludes_missing_rows() -> None:
    """Cells should be computed on the *complete-case* sub-frame per axis."""
    df = _synthetic_df(n=30)
    df.loc[0:4, "motivation_z"] = None  # 5 missing motivation
    cells = compute_correlation_matrix(df)
    cell = next(
        c for c in cells if c.axis_key == "motivation" and c.exam_metric_key == "total_score"
    )
    assert cell.n == 25


# ----------------------------------------------------------------------
# n<20 unstable inference flag
# ----------------------------------------------------------------------


def test_n_lt_20_marks_unstable_inference_flag() -> None:
    df = _synthetic_df(n=15)
    cells = compute_correlation_matrix(df)
    assert all(c.unstable_inference_flag for c in cells)


def test_n_ge_20_does_not_mark_unstable() -> None:
    df = _synthetic_df(n=50)
    cells = compute_correlation_matrix(df)
    assert all(not c.unstable_inference_flag for c in cells)


# ----------------------------------------------------------------------
# BH-FDR consistency with scipy reference
# ----------------------------------------------------------------------


def test_fdr_q_matches_scipy_false_discovery_control() -> None:
    df = _synthetic_df(n=60, seed=7)
    cells = compute_correlation_matrix(df)
    raw_ps = [c.raw_p for c in cells]
    expected_q = false_discovery_control(np.asarray(raw_ps), method="bh")
    for cell, q in zip(cells, expected_q):
        assert math.isclose(cell.fdr_q, float(q), abs_tol=1e-6)


def test_significant_after_correction_thresholds_at_005() -> None:
    df = _synthetic_df(n=60, seed=7)
    cells = compute_correlation_matrix(df)
    for cell in cells:
        assert cell.significant_after_correction == (cell.fdr_q is not None and cell.fdr_q < 0.05)


# ----------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------


def test_n_lt_3_yields_none_pearson() -> None:
    """scipy.stats.pearsonr raises for n<3; the helper must return None."""
    df = _synthetic_df(n=2)
    cells = compute_correlation_matrix(df)
    assert all(c.pearson_r is None and c.raw_p is None for c in cells)


def test_n_zero_yields_all_none_and_not_significant() -> None:
    """All axis_z columns NaN ⇒ n=0 pairwise ⇒ V1 invariant."""
    df = _synthetic_df(n=30)
    for axis in STANDARD_AXIS_KEYS:
        df[f"{axis}_z"] = None
    cells = compute_correlation_matrix(df)
    for cell in cells:
        assert cell.n == 0
        assert cell.pearson_r is None
        assert cell.raw_p is None
        assert cell.fdr_q is None
        assert cell.significant_after_correction is False


def test_constant_axis_z_yields_none_pearson() -> None:
    """Zero-variance axis ⇒ scipy raises ConstantInputWarning + returns NaN.
    Helper must surface this as None (Fail-Soft for stats edge cases)."""
    df = _synthetic_df(n=30)
    df["motivation_z"] = 0.0  # constant
    cells = compute_correlation_matrix(df)
    motivation_cells = [c for c in cells if c.axis_key == "motivation"]
    for cell in motivation_cells:
        assert cell.pearson_r is None
        assert cell.raw_p is None


def test_deterministic_cell_order(_synthetic_df_factory=_synthetic_df) -> None:
    """Order of returned cells is deterministic — research §R9 inheritance."""
    cells1 = compute_correlation_matrix(_synthetic_df_factory(n=30, seed=1))
    cells2 = compute_correlation_matrix(_synthetic_df_factory(n=30, seed=1))
    pairs1 = [(c.axis_key, c.exam_metric_key) for c in cells1]
    pairs2 = [(c.axis_key, c.exam_metric_key) for c in cells2]
    assert pairs1 == pairs2
    # And axes appear in STANDARD_AXIS_KEYS order.
    seen_axes_in_order: list[str] = []
    for axis_key, _ in pairs1:
        if not seen_axes_in_order or seen_axes_in_order[-1] != axis_key:
            seen_axes_in_order.append(axis_key)
    assert seen_axes_in_order == list(STANDARD_AXIS_KEYS)


def test_only_exam_takers_included() -> None:
    """결시 학생 (exam_taken=False) 은 상관 계산에서 제외 (FR-005)."""
    df = _synthetic_df(n=30)
    df.loc[0:9, "exam_taken"] = False  # 10 결시
    df.loc[0:9, "total_score"] = None
    cells = compute_correlation_matrix(df)
    cell = next(
        c for c in cells if c.axis_key == "motivation" and c.exam_metric_key == "total_score"
    )
    assert cell.n == 20
