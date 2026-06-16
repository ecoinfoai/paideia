"""Contract test — report §1+§2+§3+§6 + §4/§5 placeholder + 캡션 100% (T034, US1).

본 contract 는 ``combine.report_md.build_us1_report`` 의 출력이 spec.md
FR-002 / FR-004 + SC-004(c) 의 보고서 6-section 구조 + 캡션 100% 정합
을 담보한다. T030 unit test 는 *함수 호출 boundary* 검증; T034 는 *spec
contract 차원* 의 정적 정합 게이트.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from immersio.combine.report_md import build_us1_report
from paideia_shared.schemas import (
    CombinedAnalysisManifest,
    CorrelationCell,
    RegressionCoefficient,
    RegressionFitSummary,
)
from paideia_shared.schemas._common import STANDARD_AXIS_KEYS

_SHA = "0" * 64


def _manifest() -> CombinedAnalysisManifest:
    return CombinedAnalysisManifest(
        schema_version="0.1.0",
        module_version="immersio/0.1.0",
        semester="2026-1",
        course_slug="anatomy",
        generated_at_utc="2026-04-30T00:00:00Z",
        factor_scores_sha256=_SHA,
        cluster_assignment_sha256=_SHA,
        cluster_names_sha256=_SHA,
        student_metrics_sha256=_SHA,
        student_master_sha256=_SHA,
        diagnostic_response_sha256=_SHA,
        n_students_combined=30,
        n_diagnostic_only=3,
        n_exam_only=5,
        n_both=22,
        n_neither=0,
        n_unmatched_factor_scores=0,
        n_unmatched_cluster_assignment=0,
        n_unmatched_student_metrics=0,
        n_off_roster_respondents=0,
        ruleset_version="0.1.0",
        regression_method="OLS",
        multiple_comparison_method="BH-FDR",
        posthoc_method_used="Games_Howell",
        run_seed=0,
        needs_map_schema_version="1.1.0",
        immersio_phase2_schema_version="0.1.0",
        top3_predictor_axes=["motivation", "study_strategy"],
    )


def _cells() -> list[CorrelationCell]:
    return [
        CorrelationCell(
            axis_key=axis,
            exam_metric_key="total_score",
            n=22,
            pearson_r=0.3,
            raw_p=0.01,
            fdr_q=0.04,
            significant_after_correction=True,
            unstable_inference_flag=False,
        )
        for axis in STANDARD_AXIS_KEYS
    ]


def _coefs() -> list[RegressionCoefficient]:
    return [
        RegressionCoefficient(
            axis_key=axis,
            coef=1.0,
            std_err=0.5,
            t_stat=2.0,
            raw_p=0.05,
            fdr_q=0.04,
            ci_low_95=0.0,
            ci_high_95=2.0,
            beta_standardized=0.2,
            vif=1.5,
            multicollinearity_flag=False,
        )
        for axis in STANDARD_AXIS_KEYS
    ]


def _fit() -> RegressionFitSummary:
    return RegressionFitSummary(
        n_complete_case=22,
        n_dropped=8,
        r2=0.45,
        r2_adj=0.32,
        f_stat=5.0,
        f_pvalue=0.001,
        regression_method="OLS",
        multiple_comparison_method="BH-FDR",
        small_sample_warning=True,
    )


@pytest.fixture(scope="module")
def report_text(tmp_path_factory: pytest.TempPathFactory) -> str:
    out = tmp_path_factory.mktemp("contract_report") / "report.md"
    build_us1_report(
        manifest=_manifest(),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={
            "top3_axes": ["motivation", "study_strategy"],
            "prescriptive_text": "권고 텍스트.",
        },
        fig3_path=Path("figs/fig3_corr_heatmap.png"),
        fig4_path=Path("figs/fig4_beta_bar.png"),
        out_path=out,
    )
    return out.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Spec §1+§2+§3+§4+§5+§6 (4 active + 2 placeholders)
# ----------------------------------------------------------------------


def test_section_1_present(report_text: str) -> None:
    assert re.search(r"^## 1\. 분석 개요", report_text, re.MULTILINE)


def test_section_2_present(report_text: str) -> None:
    assert re.search(r"^## 2\. 상관 매트릭스", report_text, re.MULTILINE)


def test_section_3_present(report_text: str) -> None:
    assert re.search(r"^## 3\. 회귀 결과", report_text, re.MULTILINE)


def test_section_4_placeholder_present(report_text: str) -> None:
    """US1 partial mode 에서도 §4 헤더는 존재 — 학과 회의 6-섹션 일관성."""
    assert re.search(r"^## 4\. 군집별", report_text, re.MULTILINE)
    # placeholder marker
    assert "(US2 미수행)" in report_text


def test_section_5_placeholder_present(report_text: str) -> None:
    assert re.search(r"^## 5\. 부분군", report_text, re.MULTILINE)
    assert "(US4 미수행)" in report_text


def test_section_6_present(report_text: str) -> None:
    assert re.search(r"^## 6\.", report_text, re.MULTILINE)


def test_sections_appear_in_order(report_text: str) -> None:
    order: list[int] = []
    for n in range(1, 7):
        m = re.search(rf"^## {n}\. ", report_text, re.MULTILINE)
        assert m is not None, f"missing section {n}"
        order.append(m.start())
    assert order == sorted(order), f"sections out of order: {order}"


# ----------------------------------------------------------------------
# SC-004(c) — captions on every figure / table
# ----------------------------------------------------------------------


def test_every_figure_has_caption(report_text: str) -> None:
    """SC-004(c): 모든 ![alt](path) 의 alt non-empty."""
    refs = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", report_text)
    assert refs, "no figures found in report"
    for alt, path in refs:
        assert alt.strip(), f"figure {path!r} missing alt text caption"


def test_required_figs_referenced(report_text: str) -> None:
    """fig3 + fig4 PNG 가 §2 / §3 에 인라인."""
    assert "fig3_corr_heatmap.png" in report_text
    assert "fig4_beta_bar.png" in report_text


# ----------------------------------------------------------------------
# Manifest provenance — §1 audit + §6 reproducibility
# ----------------------------------------------------------------------


def test_section_1_has_six_sha256(report_text: str) -> None:
    """All 6 input SHA256 (cluster_names_sha256 GAP-10 포함) must appear in §1."""
    occurrences = report_text.count(_SHA)
    assert occurrences >= 6, f"expected ≥6 SHA256 occurrences in §1, got {occurrences}"


def test_section_1_has_r10_audit_counts(report_text: str) -> None:
    for label in (
        "n_students_combined",
        "n_unmatched_factor_scores",
        "n_unmatched_cluster_assignment",
        "n_unmatched_student_metrics",
        "n_off_roster_respondents",
    ):
        assert label in report_text, f"§1 missing R-10 audit label {label!r}"


def test_section_6_carries_reproducibility_meta(report_text: str) -> None:
    assert "ruleset_version" in report_text
    assert "module_version" in report_text
    assert "needs_map_schema_version" in report_text
    assert "immersio_phase2_schema_version" in report_text
