"""needs-map 군집 × 시험 점수 비교 — ANOVA + Tukey HSD/Games-Howell (T038, US2).

FR-019 (군집간 비교 + 사후), research §R3 (Games-Howell 수동 구현 —
``scipy.stats.studentized_range.sf`` 사용, scikit-posthocs 거부), §R6 #8
(Phase 1+2 ``levene_then_anova`` + ``welch_anova_manual`` + ``welch_t_test``
직접 inherit).

Public:
- :func:`compute_cluster_score_comparison(df, cluster_names)` →
  ``(rows, header, pairwise)`` — xlsx 군집비교 시트 3-block 직렬화.

Branching:
- k=1 → header.test_used="N/A", pairwise=[]
- k=2 → header.test_used="Welch_t_test", posthoc="N/A", pairwise=[(0,1)]
- k≥3 등분산 (levene p≥0.05) → "ANOVA" + Tukey HSD (scipy)
- k≥3 이분산 (levene p<0.05) → "Welch_ANOVA" + Games-Howell (manual)

n<5 cluster auto-exclude (FR-019): row.excluded_reason 채움; pair-wise
posthoc 에서 제외.

Determinism vector #8: pair iteration order = (i, j) ascending sorted.

Fail-Fast (qa Rule 5 페어):
- cluster_names dict empty → ValueError
- cluster_assignment 의 cluster_id 가 cluster_names 에 없음 → ValueError
- exam_taken=True + cluster_id non-null 학생 0 명 → ValueError
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd
from paideia_shared.schemas.cluster_score_comparison import (
    ClusterPairwise,
    ClusterRow,
    ClusterScoreComparison,
)
from scipy.stats import (
    f_oneway,
    levene,
    studentized_range,
    tukey_hsd,
)
from scipy.stats import (
    t as t_dist,
)

from immersio.analysis.stat_tests import welch_anova_manual, welch_t_test

from .effect_sizes import eta_squared
from .fdr import bh_fdr_adjust

_LEVENE_ALPHA = 0.05
_MIN_CLUSTER_N = 5  # FR-019 auto-exclude threshold
_SIGNIFICANCE = 0.05


def _ci_95(values: np.ndarray) -> tuple[float, float]:
    """Two-sided 95% CI for the mean — t-distribution (n>=2)."""
    n = values.size
    if n < 2:
        m = float(values[0]) if n == 1 else 0.0
        return (m, m)
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    se = sd / math.sqrt(n)
    crit = float(t_dist.ppf(0.975, n - 1))
    return (mean - crit * se, mean + crit * se)


def _build_row(
    cluster_id: int,
    label: str,
    values: np.ndarray,
    excluded_reason: str | None = None,
) -> ClusterRow:
    n = values.size
    if n == 0 or excluded_reason is not None:
        return ClusterRow(
            cluster_id=cluster_id,
            cluster_label=label,
            n=n,
            excluded_reason=excluded_reason,
        )
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if n >= 2 else 0.0
    ci_low, ci_high = _ci_95(values)
    return ClusterRow(
        cluster_id=cluster_id,
        cluster_label=label,
        n=n,
        mean=mean,
        std=std,
        ci_low_95=ci_low,
        ci_high_95=ci_high,
    )


def _games_howell_pair(g1: np.ndarray, g2: np.ndarray, k_groups: int) -> tuple[float, float]:
    """Manual Games-Howell pairwise comparison (research §R3).

    Returns ``(mean_diff, p_value)`` where p is computed via the
    studentized range distribution (Welch t-statistic transformed onto
    the q distribution): ``q = |t| · sqrt(2)``, with df_welch from the
    Welch-Satterthwaite approximation.
    """
    n1, n2 = g1.size, g2.size
    m1, m2 = float(g1.mean()), float(g2.mean())
    v1 = float(g1.var(ddof=1))
    v2 = float(g2.var(ddof=1))
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0.0:
        return m1 - m2, 1.0
    t_stat = (m1 - m2) / se
    df = ((v1 / n1 + v2 / n2) ** 2) / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    q = abs(t_stat) * math.sqrt(2.0)
    p = float(studentized_range.sf(q, k_groups, df))
    return (m1 - m2, max(0.0, min(1.0, p)))


def _validate_inputs(df: pd.DataFrame, cluster_names: Mapping[int, str]) -> pd.DataFrame:
    """Filter to exam takers + cluster_id present + Fail-Fast on bad inputs."""
    if not cluster_names:
        raise ValueError("compute_cluster_score_comparison: cluster_names sidecar is empty")
    if df.empty:
        raise ValueError("compute_cluster_score_comparison: empty input DataFrame")

    work = df[df["exam_taken"].astype(bool)].copy() if "exam_taken" in df.columns else df.copy()
    work = work[work["cluster_id"].notna()].copy()
    work = work[work["total_score"].notna()].copy()

    if work.empty:
        raise ValueError(
            "compute_cluster_score_comparison: no exam-taking respondents with cluster_id assigned"
        )

    used_cluster_ids = sorted({int(c) for c in work["cluster_id"].unique()})
    missing = [cid for cid in used_cluster_ids if cid not in cluster_names]
    if missing:
        raise ValueError(
            f"compute_cluster_score_comparison: cluster_names sidecar missing "
            f"labels for cluster_id(s) {missing}"
        )

    work["cluster_id"] = work["cluster_id"].astype(int)
    work["total_score"] = work["total_score"].astype(float)
    return work


def _eta_squared_safe(arrays: list[np.ndarray]) -> float | None:
    all_vals = np.concatenate(arrays)
    ss_total = float(((all_vals - all_vals.mean()) ** 2).sum())
    ss_between = float(sum(arr.size * (arr.mean() - all_vals.mean()) ** 2 for arr in arrays))
    ssw = ss_total - ss_between
    if (ss_between + ssw) <= 0:
        return None
    try:
        eta = eta_squared(ss_between, ssw)
    except ValueError:
        return None
    return max(0.0, min(1.0, eta))


def _enumerate_pairs(
    eligible_ids: list[int],
) -> list[tuple[int, int, int, int]]:
    """Yield ``(i, j, cid_i, cid_j)`` with ``i<j`` ascending — vector #8."""
    out: list[tuple[int, int, int, int]] = []
    for i in range(len(eligible_ids)):
        for j in range(i + 1, len(eligible_ids)):
            out.append((i, j, eligible_ids[i], eligible_ids[j]))
    return out


def compute_cluster_score_comparison(
    df: pd.DataFrame,
    cluster_names: Mapping[int, str],
) -> tuple[list[ClusterRow], ClusterScoreComparison, list[ClusterPairwise]]:
    """Compute the 3-block 군집비교 sheet output (T038).

    Args:
        df: Joiner output DataFrame (subset is fine — must carry
            ``student_id``, ``exam_taken``, ``total_score``, ``cluster_id``).
        cluster_names: SPEC-GAP-001 sidecar dict.

    Returns:
        ``(rows, header, pairwise)`` — caller (T041 xlsx + T040 report_md)
        renders this as the 군집비교 시트 3 blocks.
    """
    work = _validate_inputs(df, cluster_names)
    used_cluster_ids = sorted(work["cluster_id"].unique())
    k_total = len(used_cluster_ids)

    rows: list[ClusterRow] = []
    eligible: dict[int, np.ndarray] = {}
    for cid in used_cluster_ids:
        subset = work[work["cluster_id"] == cid]["total_score"].to_numpy(dtype=float)
        label = cluster_names[int(cid)]
        if subset.size < _MIN_CLUSTER_N:
            rows.append(
                _build_row(
                    int(cid),
                    label,
                    subset,
                    excluded_reason=(f"n < 5 군집 자동 제외 (n={subset.size})"),
                )
            )
        else:
            rows.append(_build_row(int(cid), label, subset))
            eligible[int(cid)] = subset

    pairwise: list[ClusterPairwise] = []
    eligible_ids = sorted(eligible)

    if k_total == 1:
        header = ClusterScoreComparison(
            k_used=1,
            test_used="N/A",
            levene_p=None,
            test_stat=None,
            raw_p=None,
            eta_squared=None,
            omega_squared=None,
            posthoc_test="N/A",
        )
        return rows, header, pairwise

    if len(eligible_ids) < 2:
        header = ClusterScoreComparison(
            k_used=k_total,
            test_used="N/A",
            levene_p=None,
            test_stat=None,
            raw_p=None,
            eta_squared=None,
            omega_squared=None,
            posthoc_test="N/A",
        )
        return rows, header, pairwise

    # k_total=2 — Welch's t-test (single pair).
    if k_total == 2 and len(eligible_ids) == 2:
        a_id, b_id = eligible_ids
        a, b = eligible[a_id], eligible[b_id]
        p = welch_t_test(a, b)
        mean_diff = float(a.mean() - b.mean())
        qs = bh_fdr_adjust([p])
        pairwise.append(
            ClusterPairwise(
                cluster_pair=(a_id, b_id),
                mean_diff=mean_diff,
                raw_p=p,
                fdr_q=qs[0],
                significant_after_correction=qs[0] < _SIGNIFICANCE,
            )
        )
        header = ClusterScoreComparison(
            k_used=2,
            test_used="Welch_t_test",
            levene_p=None,
            test_stat=None,
            raw_p=p,
            eta_squared=None,
            omega_squared=None,
            posthoc_test="N/A",
        )
        return rows, header, pairwise

    # k_total ≥ 3 — Levene → ANOVA / Welch_ANOVA dispatch.
    arrays = [eligible[cid] for cid in eligible_ids]
    levene_p = float(levene(*arrays, center="median").pvalue)
    homoscedastic = levene_p >= _LEVENE_ALPHA

    pair_specs = _enumerate_pairs(eligible_ids)

    if homoscedastic:
        f_res = f_oneway(*arrays)
        test_stat = float(f_res.statistic)
        anova_p = float(f_res.pvalue)
        test_used = "ANOVA"
        eta_sq = _eta_squared_safe(arrays)

        tukey = tukey_hsd(*arrays)
        raw_ps: list[float] = []
        diffs: list[float] = []
        for i, j, _cid_a, _cid_b in pair_specs:
            raw_ps.append(float(tukey.pvalue[i, j]))
            diffs.append(float(arrays[i].mean() - arrays[j].mean()))
        qs = bh_fdr_adjust(raw_ps)
        for (_i, _j, cid_a, cid_b), diff, p, q in zip(pair_specs, diffs, raw_ps, qs, strict=False):
            pairwise.append(
                ClusterPairwise(
                    cluster_pair=(cid_a, cid_b),
                    mean_diff=diff,
                    raw_p=p,
                    fdr_q=q,
                    significant_after_correction=q < _SIGNIFICANCE,
                )
            )
        posthoc = "Tukey_HSD"
    else:
        anova_p = welch_anova_manual(arrays)
        test_used = "Welch_ANOVA"
        test_stat = None
        eta_sq = _eta_squared_safe(arrays)

        k_groups = len(arrays)
        raw_ps_gh: list[float] = []
        diffs: list[float] = []
        for i, j, _cid_a, _cid_b in pair_specs:
            diff, p = _games_howell_pair(arrays[i], arrays[j], k_groups)
            diffs.append(diff)
            raw_ps_gh.append(p)
        qs = bh_fdr_adjust(raw_ps_gh)
        for (_i, _j, cid_a, cid_b), diff, p, q in zip(
            pair_specs, diffs, raw_ps_gh, qs, strict=False
        ):
            pairwise.append(
                ClusterPairwise(
                    cluster_pair=(cid_a, cid_b),
                    mean_diff=diff,
                    raw_p=p,
                    fdr_q=q,
                    significant_after_correction=q < _SIGNIFICANCE,
                )
            )
        posthoc = "Games_Howell"

    header = ClusterScoreComparison(
        k_used=k_total,
        test_used=test_used,
        levene_p=levene_p,
        test_stat=test_stat,
        raw_p=anova_p,
        eta_squared=eta_sq,
        omega_squared=None,
        posthoc_test=posthoc,
    )
    return rows, header, pairwise


__all__ = ["compute_cluster_score_comparison"]
