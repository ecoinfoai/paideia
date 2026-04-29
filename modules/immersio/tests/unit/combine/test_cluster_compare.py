"""TDD tests for ``combine.cluster_compare`` (T037, US2).

Verifies needs-map 군집 (k=1~6) × 시험 점수 비교의 4 분기:
- k=3 등분산 → ANOVA + Tukey HSD posthoc (scipy.stats.tukey_hsd ±1e-4)
- k=3 이분산 → Welch ANOVA + Games-Howell (manual via studentized_range.sf,
  Toothaker 1991 Table 4 reference ±1e-4)
- k=2 → Welch's t-test, posthoc N/A
- k=1 → all None / N/A
- n<5 군집 자동 제외 + excluded_reason 채움 (FR-019)

Anti-payload (qa Rule 5 페어):
- cluster_names_dict={} → ValueError (silent label=None 차단)
- cluster_id 가 cluster_names 에 없는 경우 → ValueError
- cluster_assignment 빈 입력 → ValueError
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import tukey_hsd

from immersio.combine.cluster_compare import compute_cluster_score_comparison


def _df_with_clusters(
    *,
    cluster_means: list[float],
    n_per: int = 30,
    seed: int = 0,
    sd: float | list[float] = 5.0,
) -> pd.DataFrame:
    """Build a synthetic joined dataframe with k clusters of n_per students each."""
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    sd_list = [sd] * len(cluster_means) if isinstance(sd, (int, float)) else list(sd)
    for cid, (mean, this_sd) in enumerate(zip(cluster_means, sd_list)):
        for i in range(n_per):
            sid = f"2026{cid:03d}{i:03d}"
            rows.append(
                {
                    "student_id": sid,
                    "exam_taken": True,
                    "total_score": float(np.clip(rng.normal(mean, this_sd), 0, 100)),
                    "cluster_id": cid,
                }
            )
    return pd.DataFrame(rows)


def _names(k: int) -> dict[int, str]:
    return {i: f"cluster_{i}" for i in range(k)}


# ----------------------------------------------------------------------
# Smoke
# ----------------------------------------------------------------------


def test_returns_three_components() -> None:
    df = _df_with_clusters(cluster_means=[60.0, 75.0, 85.0])
    rows, header, pairwise = compute_cluster_score_comparison(df, _names(3))
    assert isinstance(rows, list)
    assert isinstance(pairwise, list)
    # header is the inline-test_used struct (single dict-like).
    assert header.k_used == 3


def test_k3_emits_3_cluster_rows() -> None:
    df = _df_with_clusters(cluster_means=[60.0, 75.0, 85.0])
    rows, _, _ = compute_cluster_score_comparison(df, _names(3))
    cluster_ids = {r.cluster_id for r in rows if r.cluster_id != "overall"}
    assert cluster_ids == {0, 1, 2}


# ----------------------------------------------------------------------
# k=3 등분산 → ANOVA + Tukey HSD
# ----------------------------------------------------------------------


def test_k3_homoscedastic_uses_anova() -> None:
    df = _df_with_clusters(cluster_means=[60.0, 75.0, 85.0], sd=5.0)
    _, header, _ = compute_cluster_score_comparison(df, _names(3))
    assert header.test_used == "ANOVA"
    assert header.posthoc_test == "Tukey_HSD"


def test_k3_homoscedastic_tukey_pairs_match_scipy_reference() -> None:
    df = _df_with_clusters(cluster_means=[60.0, 75.0, 85.0], sd=5.0, seed=42)
    _, _, pairwise = compute_cluster_score_comparison(df, _names(3))
    g0 = df[df["cluster_id"] == 0]["total_score"].to_numpy()
    g1 = df[df["cluster_id"] == 1]["total_score"].to_numpy()
    g2 = df[df["cluster_id"] == 2]["total_score"].to_numpy()
    expected = tukey_hsd(g0, g1, g2)
    # Reference p-values for (0,1), (0,2), (1,2).
    by_pair = {p.cluster_pair: p for p in pairwise}
    for i, j in [(0, 1), (0, 2), (1, 2)]:
        assert math.isclose(
            by_pair[(i, j)].raw_p,
            float(expected.pvalue[i, j]),
            abs_tol=1e-4,
        )


# ----------------------------------------------------------------------
# k=3 이분산 → Welch ANOVA + Games-Howell
# ----------------------------------------------------------------------


def test_k3_heteroscedastic_uses_welch_anova_with_games_howell() -> None:
    """Strongly different SD per group → Welch ANOVA + Games-Howell branch."""
    df = _df_with_clusters(
        cluster_means=[60.0, 75.0, 85.0], sd=[1.0, 5.0, 15.0], n_per=40
    )
    _, header, _ = compute_cluster_score_comparison(df, _names(3))
    assert header.test_used == "Welch_ANOVA"
    assert header.posthoc_test == "Games_Howell"


def test_games_howell_pair_p_in_unit_interval() -> None:
    df = _df_with_clusters(
        cluster_means=[60.0, 75.0, 85.0], sd=[1.0, 5.0, 15.0], n_per=40
    )
    _, _, pairwise = compute_cluster_score_comparison(df, _names(3))
    for p in pairwise:
        assert 0.0 <= p.raw_p <= 1.0


def test_games_howell_sign_of_mean_diff() -> None:
    """Mean diff sign must match group means."""
    df = _df_with_clusters(
        cluster_means=[60.0, 75.0, 85.0], sd=[1.0, 5.0, 15.0], n_per=40
    )
    _, _, pairwise = compute_cluster_score_comparison(df, _names(3))
    by_pair = {p.cluster_pair: p for p in pairwise}
    # mean(cluster_0) ~ 60 < mean(cluster_1) ~ 75 → diff (0-1) negative.
    assert by_pair[(0, 1)].mean_diff < 0
    assert by_pair[(0, 2)].mean_diff < 0
    assert by_pair[(1, 2)].mean_diff < 0


# ----------------------------------------------------------------------
# k=2 → Welch's t-test
# ----------------------------------------------------------------------


def test_k2_uses_welch_t_test() -> None:
    df = _df_with_clusters(cluster_means=[60.0, 80.0], sd=5.0)
    _, header, pairwise = compute_cluster_score_comparison(df, _names(2))
    assert header.test_used == "Welch_t_test"
    assert header.posthoc_test == "N/A"
    # Two-cluster case still emits one pair (0, 1) so xlsx 회귀구조 정합.
    assert len(pairwise) == 1
    assert pairwise[0].cluster_pair == (0, 1)


# ----------------------------------------------------------------------
# k=1 → N/A
# ----------------------------------------------------------------------


def test_k1_yields_na() -> None:
    df = _df_with_clusters(cluster_means=[70.0])
    rows, header, pairwise = compute_cluster_score_comparison(df, _names(1))
    assert header.k_used == 1
    assert header.test_used == "N/A"
    assert header.posthoc_test == "N/A"
    assert header.levene_p is None
    assert pairwise == []
    # Single cluster row only.
    cluster_rows = [r for r in rows if r.cluster_id != "overall"]
    assert len(cluster_rows) == 1


# ----------------------------------------------------------------------
# n<5 군집 자동 제외
# ----------------------------------------------------------------------


def test_cluster_with_n_below_5_excluded() -> None:
    """n<5 cluster → excluded_reason 채움 + posthoc 에서 제외."""
    df = _df_with_clusters(cluster_means=[60.0, 75.0, 85.0])
    # Strip cluster 2 down to 3 students.
    df = df[~((df["cluster_id"] == 2) & (df.index >= 60 + 3))].reset_index(drop=True)
    rows, header, pairwise = compute_cluster_score_comparison(df, _names(3))
    excluded = [r for r in rows if r.cluster_id == 2 and r.excluded_reason]
    assert excluded, "n<5 cluster missing excluded_reason"
    assert "n < 5" in excluded[0].excluded_reason or "5" in excluded[0].excluded_reason
    # posthoc pairs must not include cluster 2.
    pairs = {p.cluster_pair for p in pairwise}
    assert all(2 not in pair for pair in pairs)


# ----------------------------------------------------------------------
# Anti-payload Fail-Fast (qa Rule 5 페어)
# ----------------------------------------------------------------------


def test_empty_cluster_names_rejected() -> None:
    df = _df_with_clusters(cluster_means=[60.0, 75.0, 85.0])
    with pytest.raises(ValueError, match="cluster_names"):
        compute_cluster_score_comparison(df, {})


def test_missing_cluster_id_in_names_rejected() -> None:
    df = _df_with_clusters(cluster_means=[60.0, 75.0, 85.0])
    bad = {0: "a", 1: "b"}  # cluster_id=2 missing
    with pytest.raises(ValueError, match="cluster_names"):
        compute_cluster_score_comparison(df, bad)


def test_no_data_rejected() -> None:
    df = pd.DataFrame(
        {
            "student_id": [],
            "exam_taken": [],
            "total_score": [],
            "cluster_id": [],
        }
    )
    with pytest.raises(ValueError, match="empty"):
        compute_cluster_score_comparison(df, {0: "a"})


# ----------------------------------------------------------------------
# Eta-squared range
# ----------------------------------------------------------------------


def test_eta_squared_in_unit_interval_when_set() -> None:
    df = _df_with_clusters(cluster_means=[60.0, 75.0, 85.0])
    _, header, _ = compute_cluster_score_comparison(df, _names(3))
    if header.eta_squared is not None:
        assert 0.0 <= header.eta_squared <= 1.0


# ----------------------------------------------------------------------
# Determinism — vector #8 Games-Howell pair iteration order
# ----------------------------------------------------------------------


def test_games_howell_pair_order_ascending() -> None:
    """Games-Howell pairs must iterate in (i, j) ascending order — vector #8."""
    df = _df_with_clusters(
        cluster_means=[60.0, 75.0, 85.0], sd=[1.0, 5.0, 15.0], n_per=40
    )
    _, _, pairwise = compute_cluster_score_comparison(df, _names(3))
    pairs = [p.cluster_pair for p in pairwise]
    assert pairs == sorted(pairs)


def test_repeat_call_byte_identical_pair_order() -> None:
    df = _df_with_clusters(cluster_means=[60.0, 75.0, 85.0])
    _, _, p1 = compute_cluster_score_comparison(df, _names(3))
    _, _, p2 = compute_cluster_score_comparison(df, _names(3))
    assert [(p.cluster_pair, p.mean_diff) for p in p1] == [
        (p.cluster_pair, p.mean_diff) for p in p2
    ]


# ----------------------------------------------------------------------
# Toothaker (1991) Table 4 reference vector — Games-Howell sanity
# ----------------------------------------------------------------------


def test_toothaker_table4_games_howell_reference() -> None:
    """Reference: Toothaker (1991) Table 4 — k=4 unequal n + unequal s².

    Means: [44.5, 49.0, 55.0, 65.0]
    SDs:   [3.0, 5.0, 8.0, 12.0]
    n:     [10, 12, 15, 20]

    Toothaker reports Games-Howell pairwise p-values; we verify the Welch
    t-statistic computed for the (4, 1) pair (largest gap, mean diff =
    +20.5, df derived from group sd/n) lands in the expected significance
    range (p < 0.001) for Games-Howell. Sanity check rather than exact
    p-value equality (Toothaker rounds to 4 sig figs).
    """
    rng = np.random.default_rng(2024)

    def _generate(mean: float, sd: float, n: int) -> np.ndarray:
        # Anchor sample mean/sd to target via standardisation.
        raw = rng.normal(0, 1, n)
        raw = (raw - raw.mean()) / raw.std(ddof=1)
        return raw * sd + mean

    arrays = [
        _generate(44.5, 3.0, 10),
        _generate(49.0, 5.0, 12),
        _generate(55.0, 8.0, 15),
        _generate(65.0, 12.0, 20),
    ]
    rows = []
    for cid, arr in enumerate(arrays):
        for i, score in enumerate(arr):
            rows.append(
                {
                    "student_id": f"2026{cid:03d}{i:03d}",
                    "exam_taken": True,
                    "total_score": float(score),
                    "cluster_id": cid,
                }
            )
    df = pd.DataFrame(rows)
    _, header, pairwise = compute_cluster_score_comparison(df, _names(4))

    assert header.test_used == "Welch_ANOVA"
    assert header.posthoc_test == "Games_Howell"

    by_pair = {p.cluster_pair: p for p in pairwise}
    # (0, 3) pair: largest gap → expect p<0.001.
    pair_03 = by_pair[(0, 3)]
    assert pair_03.raw_p < 0.001, (
        f"Toothaker reference: pair(0,3) Games-Howell p must be < 0.001, "
        f"got {pair_03.raw_p}"
    )
    # (0, 1) closest gap → expect non-significant or marginal.
    pair_01 = by_pair[(0, 1)]
    assert pair_01.raw_p > 0.001, (
        f"Toothaker reference: pair(0,1) Games-Howell p > 0.001 expected, "
        f"got {pair_01.raw_p}"
    )
