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
"""

from __future__ import annotations

from collections.abc import Sequence

from paideia_shared.schemas import RegressionCoefficient, RegressionFitSummary

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
            parts.append(
                f"가용한 유의 축 {len(top3)}개 (q<{_SIGNIFICANCE_THRESHOLD}):"
            )
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


__all__ = ["build_recommendations"]
