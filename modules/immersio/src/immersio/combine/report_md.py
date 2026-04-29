"""결합분석보고서.md writer — 6 sections fixed order (T030, US1 sections §1+§2+§3+§6).

FR-002 / FR-004 / SC-004(c). §4 (군집별, T040) + §5 (부분군, T054) 는
후속 phase 가 추가; 본 모듈은 US1 partial 모드의 4 섹션 (§1, §2, §3, §6)
+ §4/§5 placeholder 를 land.

결정성:
- 모든 입력은 sorted/ordered (correlation_cells, regression_coefs 모두
  caller 가 deterministic 순서로 land — research §R5/§R9 정합)
- 시각 path 는 caller 가 결정 — 본 모듈은 alt text + 상대 경로만 작성
- 트레일링 newline 1개 (POSIX text-file convention)
- write_text(... encoding='utf-8') — 인코딩 byte-identical
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from paideia_shared.schemas import (
    CombinedAnalysisManifest,
    CorrelationCell,
    RegressionCoefficient,
    RegressionFitSummary,
)


def _section_1_overview(
    manifest: CombinedAnalysisManifest,
    fit: RegressionFitSummary,
) -> str:
    return (
        "## 1. 분석 개요\n\n"
        "본 보고서는 needs-map 8 정량 축 × immersio 시험 점수의 결합 분석 결과를 정리한다.\n\n"
        "**입력 silver 의 SHA256 지문**:\n\n"
        f"- needs-map factor_scores: `{manifest.factor_scores_sha256}`\n"
        f"- needs-map cluster_assignment: `{manifest.cluster_assignment_sha256}`\n"
        f"- needs-map cluster_names sidecar: `{manifest.cluster_names_sha256}`\n"
        f"- immersio Phase 0 student_master: `{manifest.student_master_sha256}`\n"
        f"- immersio Phase 0 diagnostic_response: `{manifest.diagnostic_response_sha256}`\n"
        f"- immersio Phase 2 학생지표: `{manifest.student_metrics_sha256}`\n\n"
        "**학생 카운트 (R-10 audit 포함)**:\n\n"
        f"- n_students_combined: {manifest.n_students_combined}\n"
        f"- 진단응답+시험응시 (n_both): {manifest.n_both}\n"
        f"- 진단응답-only: {manifest.n_diagnostic_only}\n"
        f"- 시험응시-only: {manifest.n_exam_only}\n"
        f"- 둘 다 없음 (n_neither): {manifest.n_neither}\n"
        f"- 명단 외 응답자 (n_off_roster_respondents): {manifest.n_off_roster_respondents}\n"
        f"- factor_scores 미매칭 (n_unmatched_factor_scores): {manifest.n_unmatched_factor_scores}\n"
        f"- cluster_assignment 미매칭 (n_unmatched_cluster_assignment): {manifest.n_unmatched_cluster_assignment}\n"
        f"- 학생지표 미매칭 (n_unmatched_student_metrics): {manifest.n_unmatched_student_metrics}\n\n"
        "**통계 정의**:\n\n"
        f"- 회귀: {manifest.regression_method} (다중 선형회귀, 8 z-axis predictors)\n"
        f"- 다중비교 보정: {manifest.multiple_comparison_method} (q < 0.05)\n"
        f"- 사후 비교 (k≥2): {manifest.posthoc_method_used}\n"
        f"- complete-case n: {fit.n_complete_case} (n_dropped={fit.n_dropped})\n"
    )


def _section_2_correlation(
    cells: Sequence[CorrelationCell],
    fig3_path: Path,
) -> str:
    sig = [c for c in cells if c.significant_after_correction]
    sig_lines = "\n".join(
        f"  - {c.axis_key} × {c.exam_metric_key}: r={c.pearson_r:+.3f}, q={c.fdr_q:.4f}"
        for c in sig[:10]
    ) or "  - 유의 셀 없음 (q ≥ 0.05 across 모든 셀)"

    return (
        "## 2. 상관 매트릭스\n\n"
        f"![상관 매트릭스 heatmap (Pearson r, * = q<0.05)]({fig3_path.as_posix()})\n\n"
        "**유의 (q<0.05) 셀 일부 인용**:\n\n"
        f"{sig_lines}\n\n"
        f"전체 {len(cells)}개 셀의 Pearson r + n + q 는 `결합분석.xlsx` 의 "
        "`상관매트릭스` 시트 참조. n<20 셀은 `unstable_inference_flag=True` 로 "
        "별도 표시 (FR-005).\n"
    )


def _section_3_regression(
    coefs: Sequence[RegressionCoefficient],
    fit: RegressionFitSummary,
    fig4_path: Path,
) -> str:
    lines = "\n".join(
        f"| {c.axis_key} | {c.coef:+.3f} | {c.std_err:.3f} | "
        f"{c.t_stat:+.3f} | {c.raw_p:.4f} | {c.fdr_q:.4f} | "
        f"[{c.ci_low_95:+.3f}, {c.ci_high_95:+.3f}] | "
        f"{c.beta_standardized:+.3f} | {c.vif:.2f} |"
        for c in coefs
    )
    warn = ""
    if fit.small_sample_warning:
        warn += "\n⚠ small_sample_warning: complete-case n<30 — 추정 안정성 제한적."
    if any(c.multicollinearity_flag for c in coefs):
        warn += "\n⚠ multicollinearity_flag: 일부 axis VIF>10 — 독립 해석 주의."

    return (
        "## 3. 회귀 결과\n\n"
        f"![회귀 표준화 β bar chart (q<0.05 진한 색)]({fig4_path.as_posix()})\n\n"
        f"**적합 지표**: R²={fit.r2:.3f} (adj={fit.r2_adj:.3f}), "
        f"F={fit.f_stat:.2f} (p={fit.f_pvalue:.4g}), "
        f"n_complete_case={fit.n_complete_case}.\n\n"
        "| axis | coef | SE | t | raw_p | fdr_q | 95% CI | std_β | VIF |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        f"{lines}\n"
        f"{warn}\n"
    )


def _section_4_placeholder() -> str:
    return (
        "## 4. 군집별 비교\n\n"
        "(US2 미수행). 본 partial run 에는 포함되지 않음 — T040/T042 land 시 추가.\n"
    )


def _section_4_clusters(
    cluster_rows: object,
    cluster_header: object,
    cluster_pairwise: object,
    fig5_path: object,
) -> str:
    """T040 — §4 군집별 비교 (US2 wiring).

    cluster_rows / cluster_header / cluster_pairwise 는 forward-typing
    (객체 attribute access) 으로 받는다 — Pydantic schema (M5) 의
    ClusterRow / ClusterScoreComparison / ClusterPairwise 를 caller 가
    전달.
    """
    rows_lines = "\n".join(
        f"| {r.cluster_id} | {r.cluster_label} | {r.n} | "
        f"{'-' if r.mean is None else f'{r.mean:.2f}'} | "
        f"{'-' if r.std is None else f'{r.std:.2f}'} | "
        f"{'-' if r.ci_low_95 is None else f'[{r.ci_low_95:.2f}, {r.ci_high_95:.2f}]'} | "
        f"{r.excluded_reason or '-'} |"
        for r in cluster_rows
    )

    header_text = (
        f"**검정**: k_used={cluster_header.k_used}, test={cluster_header.test_used}, "
        f"levene_p={'-' if cluster_header.levene_p is None else f'{cluster_header.levene_p:.4f}'}, "
        f"raw_p={'-' if cluster_header.raw_p is None else f'{cluster_header.raw_p:.4f}'}, "
        f"η²={'-' if cluster_header.eta_squared is None else f'{cluster_header.eta_squared:.3f}'}, "
        f"posthoc={cluster_header.posthoc_test}"
    )

    if cluster_pairwise:
        pair_lines = "\n".join(
            f"| {p.cluster_pair[0]} ↔ {p.cluster_pair[1]} | "
            f"{p.mean_diff:+.2f} | {p.raw_p:.4f} | {p.fdr_q:.4f} | "
            f"{'예' if p.significant_after_correction else '아니오'} |"
            for p in cluster_pairwise
        )
        pairwise_block = (
            "\n**사후 비교 (BH-FDR 보정 후 q<0.05 = 유의)**:\n\n"
            "| 쌍 | 평균차 | raw_p | fdr_q | 유의 |\n"
            "|---|---|---|---|---|\n"
            f"{pair_lines}\n"
        )
    else:
        pairwise_block = ""

    fig5_md = (
        f"\n![군집별 시험 점수 boxplot]({fig5_path.as_posix()})\n"
        if fig5_path is not None
        else ""
    )

    return (
        "## 4. 군집별 비교\n\n"
        f"{header_text}\n\n"
        "| cluster_id | label | n | mean | std | 95% CI | 제외 사유 |\n"
        "|---|---|---|---|---|---|---|\n"
        f"{rows_lines}\n"
        f"{pairwise_block}"
        f"{fig5_md}"
    )


def _section_5_placeholder() -> str:
    return (
        "## 5. 부분군 비교\n\n"
        "(US4 미수행). 본 partial run 에는 포함되지 않음 — T054/T056 land 시 추가.\n"
    )


def _section_5_subgroups(
    subgroup_rows: object,
    subgroup_headers: object,
    fig6_path: object,
) -> str:
    """T054 — §5 부분군 비교 (US4 wiring).

    4 메타별 sub-block — 카테고리 표 + 검정 헤더 (test / eff size / q).
    fig6 (4-panel bar) 인라인.
    """
    headers_by_meta = {h.meta_kind: h for h in subgroup_headers}
    rows_by_meta: dict[str, list[object]] = {}
    for r in subgroup_rows:
        rows_by_meta.setdefault(r.meta_kind, []).append(r)

    blocks: list[str] = []
    meta_kr = {
        "section": "분반",
        "prior_biology": "고교생물 이수 여부",
        "occupation": "직업",
        "education": "학력",
    }
    meta_order = ["section", "prior_biology", "occupation", "education"]
    for meta_kind in meta_order:
        h = headers_by_meta.get(meta_kind)
        meta_rows = rows_by_meta.get(meta_kind, [])
        if h is None:
            continue
        rows_table_lines = "\n".join(
            f"| {r.meta_value} | {r.n} | "
            f"{'-' if r.mean is None else f'{r.mean:.2f}'} | "
            f"{'-' if r.std is None else f'{r.std:.2f}'} | "
            f"{r.excluded_reason or '-'} |"
            for r in meta_rows
        )
        eff_str = (
            "-" if h.effect_size_value is None else f"{h.effect_size_value:.3f}"
        )
        q_str = "-" if h.fdr_q is None else f"{h.fdr_q:.4f}"
        sub_idx = meta_order.index(meta_kind) + 1
        block = (
            f"### 5.{sub_idx} {meta_kr[meta_kind]}\n\n"
            f"**검정**: {h.test_used}, "
            f"raw_p={'-' if h.raw_p is None else f'{h.raw_p:.4f}'}, "
            f"fdr_q={q_str}, "
            f"effect_size ({h.effect_size_kind})={eff_str}, "
            f"n_categories_compared={h.n_categories_compared}\n\n"
            "| 카테고리 | n | mean | std | 제외 사유 |\n"
            "|---|---|---|---|---|\n"
            f"{rows_table_lines}\n"
        )
        blocks.append(block)

    fig6_md = (
        f"\n![부분군별 시험 점수 4-panel bar chart]({fig6_path.as_posix()})\n"
        if fig6_path is not None
        else ""
    )
    return "## 5. 부분군 비교\n\n" + "\n".join(blocks) + fig6_md


def _section_6_recommendations(
    recommendations: dict[str, object],
    manifest: CombinedAnalysisManifest,
) -> str:
    top3 = recommendations.get("top3_axes", [])
    text = recommendations.get("prescriptive_text", "")
    cited = ""
    if top3:
        cited = "**Top-3 강예측 축** (manifest.top3_predictor_axes 정합):\n\n" + "\n".join(
            f"- {a}" for a in top3
        ) + "\n\n"
    return (
        "## 6. 한계와 권고\n\n"
        f"{cited}"
        f"{text}\n\n"
        f"본 보고서는 ruleset_version={manifest.ruleset_version}, "
        f"module_version={manifest.module_version} 으로 산출됨. "
        "재현성: needs_map_schema_version="
        f"{manifest.needs_map_schema_version}, "
        "immersio_phase2_schema_version="
        f"{manifest.immersio_phase2_schema_version}.\n"
    )


def build_us1_report(
    *,
    manifest: CombinedAnalysisManifest,
    correlation_cells: Sequence[CorrelationCell],
    regression_coefs: Sequence[RegressionCoefficient],
    regression_fit: RegressionFitSummary,
    recommendations: dict[str, object],
    fig3_path: Path,
    fig4_path: Path,
    out_path: Path,
    cluster_rows: object | None = None,
    cluster_header: object | None = None,
    cluster_pairwise: object | None = None,
    fig5_path: Path | None = None,
    subgroup_rows: object | None = None,
    subgroup_headers: object | None = None,
    fig6_path: Path | None = None,
) -> None:
    """Compose the US1 partial markdown report and land it on disk.

    Sections produced:
    - §1 분석 개요 (manifest SHA256 + counts + 통계 정의)
    - §2 상관 매트릭스 (fig3 inline + 상위 유의 셀 인용)
    - §3 회귀 결과 (fig4 inline + 8-row coef table + 적합 지표 + warnings)
    - §4 / §5 placeholders (US2 / US4 미land)
    - §6 한계와 권고 (Top-3 인용 + prescriptive text + 재현 메타)

    Args:
        manifest: Validated :class:`CombinedAnalysisManifest`.
        correlation_cells: Output of :func:`compute_correlation_matrix`.
        regression_coefs: Output of :func:`compute_ols_regression` (1st elem).
        regression_fit: Output of :func:`compute_ols_regression` (2nd elem).
        recommendations: Output of :func:`build_recommendations`.
        fig3_path: Relative path to fig3 PNG (inserted into §2 inline).
        fig4_path: Relative path to fig4 PNG (inserted into §3 inline).
        out_path: ``.md`` destination. Parent dir auto-created.

    Raises:
        ValueError: If ``correlation_cells`` is empty (Fail-Fast).
    """
    if not correlation_cells:
        raise ValueError("build_us1_report: empty correlation_cells")
    if not regression_coefs:
        raise ValueError("build_us1_report: empty regression_coefs")

    if cluster_rows is not None and cluster_header is not None:
        # Pairwise list may legitimately be empty (k=1 fallback); §4 still
        # renders the per-cluster table + omnibus header.
        section_4 = _section_4_clusters(
            cluster_rows,
            cluster_header,
            cluster_pairwise or [],
            fig5_path,
        )
    else:
        section_4 = _section_4_placeholder()

    if subgroup_rows is not None and subgroup_headers is not None:
        section_5 = _section_5_subgroups(
            subgroup_rows, subgroup_headers, fig6_path
        )
    else:
        section_5 = _section_5_placeholder()

    parts = [
        "# 진단 × 시험 결합 분석 보고서\n",
        f"**학기/과목**: {manifest.semester} / {manifest.course_slug}  ",
        f"**생성 시각 (UTC)**: {manifest.generated_at_utc}\n",
        _section_1_overview(manifest, regression_fit),
        _section_2_correlation(correlation_cells, fig3_path),
        _section_3_regression(regression_coefs, regression_fit, fig4_path),
        section_4,
        section_5,
        _section_6_recommendations(recommendations, manifest),
    ]
    text = "\n".join(parts).rstrip() + "\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")


__all__ = ["build_us1_report"]
