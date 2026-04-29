"""4-meta subgroup comparison — section · prior_biology · occupation · education (T052, US4).

FR-011 (subgroup compare with auto-route + n<10 auto-exclude),
research §R10 (R-10 매핑 — 컬럼 후보 0건 시 "(메타 미정의)" 폴백, ≠
silent skip), §R6 #8 (Phase 1+2 levene_then_anova / welch_t_test inherit).

Public:
- :func:`compute_subgroup_score_comparison(df)` →
  ``(rows, headers)`` for xlsx 부분군비교 sheet 4 sub-blocks.

Branching per meta:
- 2 categories surviving n≥10: Welch t-test + Cohen's d (M6 V1)
- 3+ categories surviving: Levene → ANOVA / Welch_ANOVA + η² (M6 V2)
- <2 categories surviving: test_used="N/A", n_categories_compared=0 (M6 V3)
- column undefined (R-10 fallback): "(메타 미정의)" row + N/A header
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.stats import f_oneway, levene

from immersio.analysis.stat_tests import welch_anova_manual, welch_t_test

from paideia_shared.schemas.subgroup_score_comparison import (
    SubgroupMetaKind,
    SubgroupRow,
    SubgroupScoreComparison,
)

from .effect_sizes import cohen_d, eta_squared
from .fdr import bh_fdr_adjust

_META_KINDS: tuple[SubgroupMetaKind, ...] = (
    "section",
    "prior_biology",
    "occupation",
    "education",
)
_LEVENE_ALPHA = 0.05
_MIN_CATEGORY_N = 10  # FR-019/§R10 — auto-exclude threshold
_SIGNIFICANCE = 0.05

# R-10 column candidate map: which df columns each meta_kind probes.
# Order matters — first non-null candidate wins.
_META_COLUMN_CANDIDATES: dict[SubgroupMetaKind, tuple[str, ...]] = {
    "section": ("section",),
    "prior_biology": ("prior_readiness_q5", "prior_readiness_q6"),
    "occupation": ("occupation", "categorical_intent_q12"),
    "education": ("education", "categorical_intent_q13"),
}


def _resolve_meta_column(
    df: pd.DataFrame, meta_kind: SubgroupMetaKind
) -> pd.Series | None:
    """Return the first candidate column with at least one non-null value."""
    for col in _META_COLUMN_CANDIDATES[meta_kind]:
        if col in df.columns and df[col].notna().any():
            return df[col]
    return None


def _build_undefined_meta_output(
    meta_kind: SubgroupMetaKind,
) -> tuple[list[SubgroupRow], SubgroupScoreComparison]:
    """R-10 fallback: column candidates all empty → '(메타 미정의)' row + N/A header."""
    row = SubgroupRow(
        meta_kind=meta_kind,
        meta_value="(메타 미정의)",
        n=0,
        excluded_reason="R-10 매핑 미정의 — 진단 응답에서 카테고리 추출 불가",
    )
    header = SubgroupScoreComparison(
        meta_kind=meta_kind,
        test_used="N/A",
        levene_p=None,
        test_stat=None,
        raw_p=None,
        fdr_q=None,
        effect_size_kind="cohen_d",  # default; V3 enforces n_cat=0 → N/A
        effect_size_value=None,
        n_categories_compared=0,
    )
    return [row], header


def _build_category_rows(
    meta_kind: SubgroupMetaKind,
    score_by_cat: dict[str, np.ndarray],
) -> tuple[list[SubgroupRow], dict[str, np.ndarray]]:
    """Build per-category SubgroupRow + return eligible dict (n≥10)."""
    rows: list[SubgroupRow] = []
    eligible: dict[str, np.ndarray] = {}
    for category in sorted(score_by_cat):
        scores = score_by_cat[category]
        n = scores.size
        if n < _MIN_CATEGORY_N:
            rows.append(
                SubgroupRow(
                    meta_kind=meta_kind,
                    meta_value=category,
                    n=n,
                    excluded_reason=f"n < 10 카테고리 자동 제외 (n={n})",
                )
            )
        else:
            mean = float(scores.mean())
            std = float(scores.std(ddof=1)) if n >= 2 else 0.0
            rows.append(
                SubgroupRow(
                    meta_kind=meta_kind,
                    meta_value=category,
                    n=n,
                    mean=mean,
                    std=std,
                )
            )
            eligible[category] = scores
    return rows, eligible


def _compare_eligible(
    meta_kind: SubgroupMetaKind,
    eligible: dict[str, np.ndarray],
) -> SubgroupScoreComparison:
    """Run the omnibus test on the eligible categories."""
    cat_count = len(eligible)
    if cat_count < 2:
        return SubgroupScoreComparison(
            meta_kind=meta_kind,
            test_used="N/A",
            levene_p=None,
            test_stat=None,
            raw_p=None,
            fdr_q=None,
            effect_size_kind="cohen_d",
            effect_size_value=None,
            n_categories_compared=0,
        )

    arrays = [eligible[k] for k in sorted(eligible)]

    if cat_count == 2:
        a, b = arrays
        p = welch_t_test(a, b)
        try:
            d = cohen_d(a, b)
        except ValueError:
            d = None
        return SubgroupScoreComparison(
            meta_kind=meta_kind,
            test_used="t_test_welch",
            levene_p=None,
            test_stat=None,
            raw_p=p,
            fdr_q=None,  # filled by caller after BH-FDR across 4 metas
            effect_size_kind="cohen_d",
            effect_size_value=d,
            n_categories_compared=2,
        )

    # 3+ categories
    levene_p = float(levene(*arrays, center="median").pvalue)
    homoscedastic = levene_p >= _LEVENE_ALPHA
    if homoscedastic:
        f_res = f_oneway(*arrays)
        test_stat = float(f_res.statistic)
        raw_p = float(f_res.pvalue)
        test_used = "ANOVA"
    else:
        raw_p = welch_anova_manual(arrays)
        test_stat = None
        test_used = "Welch_ANOVA"

    all_vals = np.concatenate(arrays)
    ss_total = float(((all_vals - all_vals.mean()) ** 2).sum())
    ss_between = float(
        sum(arr.size * (arr.mean() - all_vals.mean()) ** 2 for arr in arrays)
    )
    ssw = ss_total - ss_between
    eta = None
    if (ss_between + ssw) > 0:
        try:
            eta = eta_squared(ss_between, ssw)
            eta = max(0.0, min(1.0, eta))
        except ValueError:
            eta = None

    return SubgroupScoreComparison(
        meta_kind=meta_kind,
        test_used=test_used,
        levene_p=levene_p,
        test_stat=test_stat,
        raw_p=raw_p,
        fdr_q=None,  # filled later
        effect_size_kind="eta_squared",
        effect_size_value=eta,
        n_categories_compared=cat_count,
    )


def compute_subgroup_score_comparison(
    df: pd.DataFrame,
) -> tuple[list[SubgroupRow], list[SubgroupScoreComparison]]:
    """Compute the 4-meta subgroup × total_score comparison (T052).

    Args:
        df: Joiner output DataFrame. Must carry ``exam_taken``,
            ``total_score``, plus subgroup candidate columns
            (``section``, ``prior_readiness_q5/q6``, ``occupation``,
            ``categorical_intent_q12/q13``, ``education``).

    Returns:
        ``(rows, headers)``:
        - rows: 4-meta sub-block (per-category rows incl. excluded +
          R-10 미정의 폴백)
        - headers: 4 :class:`SubgroupScoreComparison` (one per meta_kind,
          deterministic order = ``_META_KINDS``). BH-FDR adjusted q
          across the 4 raw_p values that are not None.

    Raises:
        ValueError: If ``df`` is empty or contains zero exam takers.
    """
    if df.empty:
        raise ValueError("compute_subgroup_score_comparison: empty DataFrame")

    if "exam_taken" in df.columns:
        work = df[df["exam_taken"].astype(bool)].copy()
    else:
        work = df.copy()
    work = work[work["total_score"].notna()].copy()
    if work.empty:
        raise ValueError(
            "compute_subgroup_score_comparison: no exam-taking respondents "
            "with total_score"
        )
    work["total_score"] = work["total_score"].astype(float)

    rows: list[SubgroupRow] = []
    headers: list[SubgroupScoreComparison] = []

    for meta_kind in _META_KINDS:
        col = _resolve_meta_column(work, meta_kind)
        if col is None:
            r, h = _build_undefined_meta_output(meta_kind)
            rows.extend(r)
            headers.append(h)
            continue

        meta_df = work.assign(_meta=col).dropna(subset=["_meta"])
        if meta_df.empty:
            r, h = _build_undefined_meta_output(meta_kind)
            rows.extend(r)
            headers.append(h)
            continue

        score_by_cat: dict[str, np.ndarray] = {}
        for category, group in meta_df.groupby("_meta"):
            score_by_cat[str(category)] = group["total_score"].to_numpy(
                dtype=float
            )

        cat_rows, eligible = _build_category_rows(meta_kind, score_by_cat)
        rows.extend(cat_rows)
        headers.append(_compare_eligible(meta_kind, eligible))

    # BH-FDR across the 4 raw_p values that are populated.
    defined_idx = [i for i, h in enumerate(headers) if h.raw_p is not None]
    if defined_idx:
        ps = [headers[i].raw_p for i in defined_idx]
        qs = bh_fdr_adjust(ps)
        # Headers are frozen Pydantic — rebuild with fdr_q populated.
        adjusted: list[SubgroupScoreComparison] = []
        q_lookup = {idx: q for idx, q in zip(defined_idx, qs)}
        for i, h in enumerate(headers):
            q = q_lookup.get(i)
            adjusted.append(h.model_copy(update={"fdr_q": q}))
        headers = adjusted

    return rows, headers


__all__ = ["compute_subgroup_score_comparison"]
