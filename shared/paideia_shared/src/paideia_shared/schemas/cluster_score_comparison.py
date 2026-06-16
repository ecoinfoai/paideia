"""ClusterScoreComparison + ClusterPairwise (M5 in data-model.md, T008).

xlsx `군집비교` 시트 — (a) 군집별 행 + (b) ANOVA 헤더 + (c) 사후 비교 sub-table.
3 모델 합본:
- ``ClusterRow`` — 군집별 1 행 (cluster_id, n, mean, std, CI)
- ``ClusterScoreComparison`` — ANOVA 헤더 1 행 (k_used, test_used, F, p, η², ω², posthoc)
- ``ClusterPairwise`` — 사후 비교 1 행 (cluster_pair, mean_diff, raw_p, fdr_q)
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClusterRow(BaseModel):
    """One cluster row in xlsx `군집비교` Block 1."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: int | Literal["overall"]
    cluster_label: str
    n: int = Field(ge=0)
    mean: float | None = None
    std: float | None = None
    ci_low_95: float | None = None
    ci_high_95: float | None = None
    excluded_reason: str | None = None

    @model_validator(mode="after")
    def _v_n_zero_implies_stats_none(self) -> Self:
        """n=0 ⇒ mean/std/CI all None."""
        if self.n == 0:
            for field_name in ("mean", "std", "ci_low_95", "ci_high_95"):
                if getattr(self, field_name) is not None:
                    raise ValueError(f"ClusterRow n=0: {field_name} must be None when n=0")
        return self


class ClusterScoreComparison(BaseModel):
    """ANOVA header row (M5)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    k_used: int = Field(ge=1)
    test_used: Literal["ANOVA", "Welch_ANOVA", "Welch_t_test", "N/A"]
    levene_p: float | None = None
    test_stat: float | None = None
    raw_p: float | None = None
    eta_squared: float | None = None
    omega_squared: float | None = None
    posthoc_test: Literal["Tukey_HSD", "Games_Howell", "N/A"]

    @model_validator(mode="after")
    def _v1_k1_implies_na(self) -> Self:
        """V1: k_used=1 ⇒ test_used='N/A' AND levene_p is None AND posthoc_test='N/A'."""
        if self.k_used == 1:
            if self.test_used != "N/A":
                raise ValueError(f"V1 k=1: test_used must be 'N/A', got {self.test_used}")
            if self.levene_p is not None:
                raise ValueError(f"V1 k=1: levene_p must be None, got {self.levene_p}")
            if self.posthoc_test != "N/A":
                raise ValueError(f"V1 k=1: posthoc_test must be 'N/A', got {self.posthoc_test}")
        return self

    @model_validator(mode="after")
    def _v2_k2_implies_welch_t(self) -> Self:
        """V2: k_used=2 ⇒ test_used='Welch_t_test' AND posthoc_test='N/A'."""
        if self.k_used == 2:
            if self.test_used != "Welch_t_test":
                raise ValueError(f"V2 k=2: test_used must be 'Welch_t_test', got {self.test_used}")
            if self.posthoc_test != "N/A":
                raise ValueError(f"V2 k=2: posthoc_test must be 'N/A', got {self.posthoc_test}")
        return self

    @model_validator(mode="after")
    def _v3_eta_squared_unit_range(self) -> Self:
        """V3: eta_squared in [0, 1] when populated."""
        if self.eta_squared is not None and not (0.0 <= self.eta_squared <= 1.0):
            raise ValueError(f"V3 eta_squared range: must be in [0, 1], got {self.eta_squared}")
        return self


class ClusterPairwise(BaseModel):
    """Post-hoc pairwise comparison row (M5 sub-table)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_pair: tuple[int, int]
    mean_diff: float
    raw_p: float = Field(ge=0.0, le=1.0)
    fdr_q: float = Field(ge=0.0, le=1.0)
    significant_after_correction: bool

    @model_validator(mode="after")
    def _v_pair_ascending(self) -> Self:
        """cluster_pair must be (lo, hi) with lo < hi (deterministic)."""
        lo, hi = self.cluster_pair
        if not (lo < hi):
            raise ValueError(
                f"cluster_pair must be (lo, hi) with lo<hi for determinism, got {self.cluster_pair}"
            )
        return self


__all__ = ["ClusterRow", "ClusterScoreComparison", "ClusterPairwise"]
