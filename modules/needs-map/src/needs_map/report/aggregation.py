"""Aggregation helper that produces ``AxisSummaryRow`` instances [T037].

Single entry point :func:`build_axis_summary_rows` walks the silver-tier
artifacts (scale_reliability + factor_scores_long + the auxiliary column
counts pre-computed by Phase D + per-freetext-area summaries) and emits
the three discriminator-driven row kinds defined in
``contracts/exports.md``:

- ``quantitative`` — one row per axis present in scale_reliability.
- ``auxiliary_distribution`` — one row per (axis_key, source_col, option)
  triple, with ``percentage = count / n_responded × 100`` per spec
  FR-010 (response-rate base, NOT cohort base).
- ``freetext_summary`` — one row per freetext area (Q61 anxiety, Q62
  experience).

The helper is pure — no I/O. The pipeline (T038) joins the silver inputs
and feeds them into this function before handing the rows to
``write_axis_summary`` (T036).

Spec: 003-needs-map-v0-1-1/tasks.md T037; contracts/exports.md §3-§4.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from paideia_shared.schemas import AxisSummaryRow

_QUANT_AXIS_FIELDS_FROM_RELIABILITY = (
    "axis_key",
    "n_items",
    "cronbach_alpha",
    "reliability_label",
)


def build_axis_summary_rows(
    *,
    scale_reliability: Sequence[Mapping[str, Any]],
    factor_scores_long: Sequence[Mapping[str, Any]],
    auxiliary_columns: Mapping[str, Mapping[str, Mapping[str, int]]],
    freetext_summaries: Mapping[str, Mapping[str, Any]],
    n_cohort: int,
) -> list[AxisSummaryRow]:
    """Compose AxisSummaryRow instances from the silver-tier inputs.

    Args:
        scale_reliability: Iterable of dicts shaped like ScaleReliabilityRow
            (axis_key, n_items, cronbach_alpha, label, operational_warning,
            reliability_label).
        factor_scores_long: Iterable of FactorScoresLongRow-shaped dicts.
            Used to compute n / mean / std / quartiles per axis.
        auxiliary_columns: Pre-computed counts ``{axis_key: {source_col:
            {option: count}}}``. ``n_responded`` is derived as the sum of
            counts for that ``source_col`` (multiselect-safe — for true
            multiselect the caller passes the *number of unique responders*
            rather than the option-pick total).
        freetext_summaries: ``{axis_key: {n_responses, n_categorized,
            dictionary_match_rate, mean_negativity, top_emotion_distribution}}``.
        n_cohort: Total semester responder count (denominator for
            n_responded / n_cohort exposure).

    Returns:
        List of AxisSummaryRow instances. Caller is responsible for sort
        order; ``write_axis_summary`` re-sorts deterministically.
    """
    rows: list[AxisSummaryRow] = []

    # quantitative — driven by scale_reliability
    for rel in scale_reliability:
        axis_key = rel["axis_key"]
        stats = _compute_quant_stats(factor_scores_long, axis_key)
        rows.append(
            AxisSummaryRow(
                row_kind="quantitative",
                axis_key=axis_key,
                n=stats["n"],
                n_items=rel["n_items"],
                mean_raw=stats["mean"],
                std_raw=stats["std"],
                p25=stats["p25"],
                p50=stats["p50"],
                p75=stats["p75"],
                cronbach_alpha=rel.get("cronbach_alpha"),
                reliability_label=rel.get("reliability_label") or _label_from_alpha(rel),
            )
        )

    # auxiliary_distribution — response-rate base
    for axis_key, by_source in auxiliary_columns.items():
        for source_col, option_counts in by_source.items():
            n_responded = sum(option_counts.values())
            for option, count in option_counts.items():
                percentage = (count / n_responded * 100.0) if n_responded else 0.0
                rows.append(
                    AxisSummaryRow(
                        row_kind="auxiliary_distribution",
                        axis_key=axis_key,
                        source_col=source_col,
                        option=option,
                        count=count,
                        percentage=percentage,
                        n_responded=n_responded,
                        n_cohort=n_cohort,
                    )
                )

    # freetext_summary
    for axis_key, payload in freetext_summaries.items():
        rows.append(
            AxisSummaryRow(
                row_kind="freetext_summary",
                axis_key=axis_key,
                n_responses=payload.get("n_responses"),
                n_categorized=payload.get("n_categorized"),
                dictionary_match_rate=payload.get("dictionary_match_rate"),
                mean_negativity=payload.get("mean_negativity"),
                top_emotion_distribution=payload.get("top_emotion_distribution"),
            )
        )

    return rows


def _compute_quant_stats(long_rows: Sequence[Mapping[str, Any]], axis_key: str) -> dict[str, Any]:
    """Compute n / mean / std / p25 / p50 / p75 from the long-form rows.

    Excludes None values per axis (drop policy at the consumer side).
    Returns ``None`` for stats whose denominator is zero so the schema's
    quantitative row validator surfaces operator-actionable errors.
    """
    raw_values: list[float] = []
    for row in long_rows:
        v = row.get(f"{axis_key}_raw")
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            raw_values.append(float(v))
    n = len(raw_values)
    if n == 0:
        return {
            "n": 0,
            "mean": 0.0,
            "std": 0.0,
            "p25": 0.0,
            "p50": 0.0,
            "p75": 0.0,
        }
    sorted_values = sorted(raw_values)
    mean = sum(sorted_values) / n
    variance = sum((v - mean) ** 2 for v in sorted_values) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(variance)
    p25 = _percentile(sorted_values, 0.25)
    p50 = _percentile(sorted_values, 0.50)
    p75 = _percentile(sorted_values, 0.75)
    return {"n": n, "mean": mean, "std": std, "p25": p25, "p50": p50, "p75": p75}


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (numpy default behaviour)."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(sorted_values[int(pos)])
    weight_hi = pos - lo
    return float(sorted_values[lo] * (1.0 - weight_hi) + sorted_values[hi] * weight_hi)


def _label_from_alpha(rel: Mapping[str, Any]) -> str:
    """Derive ReliabilityLabel from raw alpha when row.reliability_label is None.

    Caller is expected to pass reliability_label explicitly; this is a
    defensive default for partial inputs.
    """
    n_items = rel.get("n_items", 0)
    if n_items in (0, 1, 2):
        return "N/A — single/double item"
    alpha = rel.get("cronbach_alpha")
    if alpha is None:
        return "N/A — single/double item"
    if alpha >= 0.80:
        return "high"
    if alpha >= 0.70:
        return "medium"
    return "low"


__all__ = ["build_axis_summary_rows"]
