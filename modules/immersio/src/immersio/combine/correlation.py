"""Pearson correlation matrix 8 axes × N exam metrics with BH-FDR (T026, US1).

FR-005 (cell-level Pearson + n<20 unstable flag), FR-007 (BH-FDR q=0.05),
research §R5 (cell-by-cell ``scipy.stats.pearsonr`` rather than pandas
``DataFrame.corr`` so that pairwise *n* is exact + scipy returns the
two-sided p-value directly).

Public API:
- :func:`compute_correlation_matrix(df)` — returns ``list[CorrelationCell]``
  ordered by ``(axis_key per STANDARD_AXIS_KEYS, exam_metric_key
  alphabetical with 'total_score' first)`` for downstream xlsx/figure
  consumers (T029 fig3 heatmap + T032 xlsx 상관매트릭스 시트).

Determinism is guaranteed via:
- iteration over ``STANDARD_AXIS_KEYS`` (constitution v1.1.0 fixed tuple)
- exam metric ordering: ``total_score`` first, then chapter rates sorted
  alphabetically by Korean key (Python string sort is byte-stable)
- BH-FDR via :func:`combine.fdr.bh_fdr_adjust` (vector #7 stable sort)
"""

from __future__ import annotations

import math
import warnings

import pandas as pd
from paideia_shared.schemas import CorrelationCell
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS
from scipy.stats import ConstantInputWarning, NearConstantInputWarning, pearsonr

from .fdr import bh_fdr_adjust

_UNSTABLE_N_THRESHOLD = 20  # FR-005


def _exam_metric_columns(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """Return ``[(metric_key, series), ...]`` in deterministic order.

    Order: ``total_score`` first, then ``chapter_<name>`` for each unique
    chapter name in ``chapter_correct_rates`` dict columns, sorted
    alphabetically (Python string sort).
    """
    out: list[tuple[str, pd.Series]] = [("total_score", df["total_score"])]

    chapter_keys: set[str] = set()
    for value in df["chapter_correct_rates"]:
        if isinstance(value, dict):
            chapter_keys.update(value.keys())

    for chapter in sorted(chapter_keys):
        col = df["chapter_correct_rates"].apply(
            lambda d, ch=chapter: d.get(ch) if isinstance(d, dict) else None
        )
        out.append((f"chapter_{chapter}", col))

    return out


def _pairwise_pearson(x: pd.Series, y: pd.Series) -> tuple[int, float | None, float | None]:
    """Compute (n, r, p) for the complete-case overlap of two series.

    Returns ``(n, None, None)`` when ``n < 3`` (scipy requires ≥ 3) or
    when either series is constant on the overlap (scipy emits
    ConstantInputWarning + NaN in that case, which we surface as None).
    """
    pair = pd.concat([x, y], axis=1).dropna()
    n = len(pair)
    if n < 3:
        return n, None, None

    xs = pair.iloc[:, 0].to_numpy(dtype=float)
    ys = pair.iloc[:, 1].to_numpy(dtype=float)

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConstantInputWarning)
        warnings.simplefilter("error", NearConstantInputWarning)
        try:
            r, p = pearsonr(xs, ys)
        except (ConstantInputWarning, NearConstantInputWarning):
            return n, None, None

    if math.isnan(r) or math.isnan(p):
        return n, None, None
    return n, float(r), float(p)


def compute_correlation_matrix(df: pd.DataFrame) -> list[CorrelationCell]:
    """Build the 8-axis × N-metric Pearson matrix with BH-FDR adjustment.

    Args:
        df: Joiner output (see :func:`combine.joiner.join_silver_phase3`).
            Must carry the 8 ``{axis}_z`` columns plus ``total_score`` and
            ``chapter_correct_rates`` (native dict).

    Returns:
        List of :class:`CorrelationCell` ordered by (axis ∈
        STANDARD_AXIS_KEYS, metric ∈ {total_score, chapter_*}). q-values
        from :func:`combine.fdr.bh_fdr_adjust` are clamped to [0, 1] and
        ``None`` for cells where the raw Pearson p was undefined.
    """
    # Restrict to exam takers — FR-005 says correlation is computed only
    # over students who have an exam score. The fixture builder already
    # leaves total_score=None for absentees; we still drop the rows so
    # pairwise n is reported on actual exam takers.
    if "exam_taken" in df.columns:
        df = df[df["exam_taken"].astype(bool)].copy()

    metrics = _exam_metric_columns(df)

    cells_partial: list[tuple[str, str, int, float | None, float | None]] = []
    for axis in STANDARD_AXIS_KEYS:
        z_col = df[f"{axis}_z"]
        for metric_key, metric_col in metrics:
            n, r, p = _pairwise_pearson(z_col, metric_col)
            cells_partial.append((axis, metric_key, n, r, p))

    # BH-FDR adjustment: scipy.stats.false_discovery_control requires no
    # NaN — substitute defined p values + carry None separately.
    defined_indices = [i for i, (_, _, _, _, p) in enumerate(cells_partial) if p is not None]
    if defined_indices:
        ps = [cells_partial[i][4] for i in defined_indices]
        qs = bh_fdr_adjust(ps)
        q_by_index: dict[int, float | None] = dict(zip(defined_indices, qs, strict=False))
    else:
        q_by_index = {}

    out: list[CorrelationCell] = []
    for i, (axis, metric_key, n, r, p) in enumerate(cells_partial):
        q = q_by_index.get(i)
        # V1 invariant: n=0 ⇒ all stats None + significant=False.
        if n == 0:
            r = None
            p = None
            q = None
        out.append(
            CorrelationCell(
                axis_key=axis,
                exam_metric_key=metric_key,
                n=n,
                pearson_r=r,
                raw_p=p,
                fdr_q=q,
                significant_after_correction=bool(q is not None and q < 0.05),
                unstable_inference_flag=n < _UNSTABLE_N_THRESHOLD,
            )
        )
    return out


__all__ = ["compute_correlation_matrix"]
