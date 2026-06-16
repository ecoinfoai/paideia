"""Cohort-level prescriptive rules — Top-3 |β| + warnings (T028, US1).

FR-017 (운영자용 §6 권고 단락), FR-018 (Top-3 강예측 축), FR-019 (단일
유의 축 인용), FR-019a (q<0.05 strict + |β| ranking + alphabetic tie-break),
research §R9 (axis_key alphabetic on |β| equal).

LLM 미사용 — rule-based templates ONLY (Constitution V "외부 의존 0").

Public API:
- :func:`build_recommendations(coefs, fit)` — returns
  ``{"top3_axes": list[str], "prescriptive_text": str}``. ``top3_axes``
  is the FR-019a output that lands directly in
  ``CombinedAnalysisManifest.top3_predictor_axes``.
- :func:`build_cluster_recommendations(cluster_rows, cluster_header)` —
  ADR-016 #7 군집 명명 인용 prose (ruleset_version 0.1.1). ANOVA/Welch
  p<0.05 일 때 cohort mean 대비 유의 차이 cluster 를 운영 prose form 으로
  인용 — Phase 5 US2 wire-in.
"""

from __future__ import annotations

from collections.abc import Sequence

from paideia_shared.schemas import (
    ClusterRow,
    ClusterScoreComparison,
    RegressionCoefficient,
    RegressionFitSummary,
)

_SIGNIFICANCE_THRESHOLD = 0.05  # FR-019a — strict <
_VIF_THRESHOLD = 10.0  # FR-013
_TOP_N = 3


def _significant_axes(
    coefs: Sequence[RegressionCoefficient],
) -> list[RegressionCoefficient]:
    """Return coefs with q < 0.05 (strict) — FR-019a."""
    return [c for c in coefs if c.fdr_q < _SIGNIFICANCE_THRESHOLD]


def _rank_top_n(
    significant: Sequence[RegressionCoefficient], n: int
) -> list[RegressionCoefficient]:
    """Sort by (-|β|, axis_key alphabetic) — research §R9 tie-breaker."""
    return sorted(
        significant,
        key=lambda c: (-abs(c.coef), c.axis_key),
    )[:n]


def _format_axis_phrase(c: RegressionCoefficient) -> str:
    """Render one axis line for the §6 prescriptive paragraph."""
    direction = "양의" if c.coef > 0 else "음의"
    return (
        f"  - {c.axis_key}: {direction} 영향 (β={c.coef:+.3f}, "
        f"q={c.fdr_q:.4f}, |β|={abs(c.coef):.3f})"
    )


def _build_text(
    *,
    top3: list[RegressionCoefficient],
    fit: RegressionFitSummary,
    multicollinearity: bool,
) -> str:
    """Compose the §6 권고 단락 text per FR-017 / FR-018 / FR-019 / FR-019a."""
    parts: list[str] = []

    if top3:
        if len(top3) >= _TOP_N:
            parts.append(
                f"Top-{_TOP_N} 강예측 축 (q<{_SIGNIFICANCE_THRESHOLD} 통과 + "
                f"|β| 상위, 동률 시 axis_key 알파벳 우선):"
            )
        else:
            parts.append(f"가용한 유의 축 {len(top3)}개 (q<{_SIGNIFICANCE_THRESHOLD}):")
        for c in top3:
            parts.append(_format_axis_phrase(c))
    else:
        parts.append(
            "BH-FDR 보정 후 통계적으로 유의한 (q<0.05) 축이 없음 — 본 학기 "
            "데이터로는 시험 점수에 대한 단일 진단 변수의 안정적 예측력을 "
            "주장할 수 없음. 학기 누적 표본 확보 후 재분석 권고."
        )

    if fit.small_sample_warning:
        parts.append(
            "\n⚠ 표본 경고: complete-case n<30 (n="
            f"{fit.n_complete_case}) — 회귀 추정 안정성 제한적. 본 권고는 "
            "다음 학기 표본 누적 후 재검증 의무."
        )

    if multicollinearity:
        parts.append(
            "\n⚠ 다중공선성 경고: 일부 axis VIF>10 — 일부 표준화 β 의 "
            "독립 해석은 불가, 그룹 단위 효과 해석 권고."
        )

    return "\n".join(parts)


def build_recommendations(
    coefs: Sequence[RegressionCoefficient],
    fit: RegressionFitSummary,
) -> dict[str, object]:
    """Build the §6 권고 단락 inputs from regression output.

    Args:
        coefs: Per-axis :class:`RegressionCoefficient` list (T027 output).
        fit: :class:`RegressionFitSummary` (T027 output).

    Returns:
        Dict with two keys:
        - ``top3_axes`` (``list[str]``): axis_key values that land in
          ``CombinedAnalysisManifest.top3_predictor_axes``.
        - ``prescriptive_text`` (``str``): §6 단락 본문.

    Raises:
        ValueError: If ``coefs`` is empty (Fail-Fast).
    """
    if not coefs:
        raise ValueError("build_recommendations: empty regression coefficient list")

    significant = _significant_axes(coefs)
    top_n = _rank_top_n(significant, _TOP_N)

    multicollinearity = any(c.vif > _VIF_THRESHOLD for c in coefs)

    text = _build_text(top3=top_n, fit=fit, multicollinearity=multicollinearity)

    return {
        "top3_axes": [c.axis_key for c in top_n],
        "prescriptive_text": text,
    }


def build_cluster_recommendations(
    cluster_rows: Sequence[ClusterRow],
    cluster_header: ClusterScoreComparison,
) -> str:
    """ADR-016 #7 — 군집 명명 인용 prose (ruleset_version 0.1.1).

    ANOVA/Welch p < 0.05 일 때 cohort weighted mean 대비 가장 높은/낮은
    군집을 운영 prose form 으로 인용. n<5 자동 제외 군집 (excluded_reason
    채워진) 은 인용 대상에서 빠짐.

    Args:
        cluster_rows: Per-cluster :class:`ClusterRow` rows (T038 output).
            n>=5 + excluded_reason is None 인 항목만 cohort 비교 후보.
        cluster_header: :class:`ClusterScoreComparison` containing
            ANOVA/Welch result fields (k_used / test_used / raw_p ...).

    Returns:
        Multi-line prose (high + low cohort 비교, ADR-016 #7 양식). ANOVA
        가 유의하지 않거나 인용 후보가 0건이면 폴백 단락 반환.
    """
    threshold = _SIGNIFICANCE_THRESHOLD  # FR-019a strict
    if cluster_header.raw_p is None or cluster_header.raw_p >= threshold:
        return (
            "본 학기 데이터로는 needs-map 군집간 시험 점수 평균 차이가 "
            f"통계적으로 유의하지 않음 (p={cluster_header.raw_p:.4f} ≥ "
            f"{threshold} 또는 단일 군집). 군집 단위 면담 우선순위 부여는 "
            "후속 학기 누적 후 재분석 권고."
            if cluster_header.raw_p is not None
            else "단일 군집 (k=1) — 군집간 비교 N/A."
        )

    valid = [
        r
        for r in cluster_rows
        if r.mean is not None
        and r.excluded_reason is None
        and r.n > 0
        and r.cluster_id != "overall"
    ]
    if not valid:
        return (
            "ANOVA 는 유의하나 n≥5 + excluded_reason 미부여 군집이 없음 — "
            "운영 prose 인용 대상 부재."
        )

    total_n = sum(r.n for r in valid)
    cohort_mean = sum(r.mean * r.n for r in valid) / total_n  # weighted

    high = max(valid, key=lambda r: r.mean)
    low = min(valid, key=lambda r: r.mean)

    parts: list[str] = []
    if high.mean > cohort_mean:
        parts.append(
            f"군집 '{high.cluster_label}' (n={high.n})의 평균 점수가 cohort "
            f"대비 유의하게 높음 — 차년도 운영 시 동 군집 학생군 추가 "
            f"모니터링 권고."
        )
    if low.cluster_id != high.cluster_id and low.mean < cohort_mean:
        parts.append(
            f"군집 '{low.cluster_label}' (n={low.n})의 평균 점수가 cohort "
            f"대비 유의하게 낮음 — 차년도 운영 시 동 군집 학생군 추가 "
            f"모니터링 권고."
        )
    if not parts:
        return (
            "ANOVA 는 유의하나 cohort weighted mean 양측 갈림 군집이 "
            "동일 — 단일 cluster 만 cohort 대비 차이. 후속 학기 재검토 권고."
        )
    return "\n".join(parts)


__all__ = ["build_recommendations", "build_cluster_recommendations"]
