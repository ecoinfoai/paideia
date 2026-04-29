"""TDD tests for ``combine.report_md`` — US1 sections §1, §2, §3, §6 (T030).

Verifies the markdown report writer:
- §1 분석 개요 (input SHA + counts + 통계 정의)
- §2 상관 매트릭스 (heatmap inline + cell excerpt + 룰 텍스트)
- §3 회귀 결과 (fit summary + coef table + 룰 텍스트)
- §6 한계와 권고 (Top-3 인용 + warnings)
- §4/§5 가 빈 상태로 land 가능 (T040/T054 추가 전)
- 표·차트 100% 캡션 부착 (SC-004(c))
- byte-identical re-run
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


def _manifest(top3: list[str] | None = None) -> CombinedAnalysisManifest:
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
        top3_predictor_axes=top3 or [],
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


def test_writes_markdown_file(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    build_us1_report(
        manifest=_manifest(),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={"top3_axes": [], "prescriptive_text": "권고 텍스트"},
        fig3_path=Path("figs/fig3_corr.png"),
        fig4_path=Path("figs/fig4_beta.png"),
        out_path=out,
    )
    assert out.exists()


def test_section_1_analysis_overview_present(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    build_us1_report(
        manifest=_manifest(),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={"top3_axes": [], "prescriptive_text": "권고"},
        fig3_path=Path("figs/fig3.png"),
        fig4_path=Path("figs/fig4.png"),
        out_path=out,
    )
    text = out.read_text(encoding="utf-8")
    assert re.search(r"## 1\. 분석 개요", text)
    # input SHA + counts must surface.
    assert _SHA in text  # at least one input sha256
    assert "n_students_combined" in text or "전체 결합 학생" in text
    assert "OLS" in text  # 통계 정의
    assert "BH-FDR" in text


def test_section_2_correlation_matrix_present(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    build_us1_report(
        manifest=_manifest(),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={"top3_axes": [], "prescriptive_text": ""},
        fig3_path=Path("figs/fig3_corr.png"),
        fig4_path=Path("figs/fig4_beta.png"),
        out_path=out,
    )
    text = out.read_text(encoding="utf-8")
    assert re.search(r"## 2\. 상관 매트릭스", text)
    # heatmap inline must reference fig3 path
    assert "fig3_corr.png" in text
    # at least one excerpt cell
    assert "Pearson" in text or "pearson" in text


def test_section_3_regression_present(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    build_us1_report(
        manifest=_manifest(),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={"top3_axes": [], "prescriptive_text": ""},
        fig3_path=Path("figs/fig3.png"),
        fig4_path=Path("figs/fig4_beta.png"),
        out_path=out,
    )
    text = out.read_text(encoding="utf-8")
    assert re.search(r"## 3\. 회귀 결과", text)
    assert "fig4_beta.png" in text
    # fit summary numbers must appear
    assert "0.45" in text or "R²" in text


def test_section_6_recommendations_present(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    build_us1_report(
        manifest=_manifest(top3=["motivation", "study_strategy"]),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={
            "top3_axes": ["motivation", "study_strategy"],
            "prescriptive_text": "권고 본문 — 학과 회의용 요약.",
        },
        fig3_path=Path("figs/fig3.png"),
        fig4_path=Path("figs/fig4.png"),
        out_path=out,
    )
    text = out.read_text(encoding="utf-8")
    assert re.search(r"## 6\. (한계와 권고|권고)", text)
    assert "권고 본문" in text


def test_sections_4_and_5_placeholders_for_us1_only_run(tmp_path: Path) -> None:
    """US1 partial 모드: §4, §5 는 placeholder 또는 부재."""
    out = tmp_path / "report.md"
    build_us1_report(
        manifest=_manifest(),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={"top3_axes": [], "prescriptive_text": ""},
        fig3_path=Path("figs/fig3.png"),
        fig4_path=Path("figs/fig4.png"),
        out_path=out,
    )
    text = out.read_text(encoding="utf-8")
    # §4 군집별 / §5 부분군 are out of scope here — should be either absent
    # or marked as placeholder ("(US2/US4 미수행)").
    # We accept either form, but they must NOT carry full content.
    assert "## 4. 군집별" not in text or "(US2 미수행)" in text or "준비 중" in text or "TBD" in text


def test_caption_100_percent_for_figures(tmp_path: Path) -> None:
    """SC-004(c): 모든 차트에 캡션 부여."""
    out = tmp_path / "report.md"
    build_us1_report(
        manifest=_manifest(),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={"top3_axes": [], "prescriptive_text": ""},
        fig3_path=Path("figs/fig3.png"),
        fig4_path=Path("figs/fig4.png"),
        out_path=out,
    )
    text = out.read_text(encoding="utf-8")
    # Each ![...](path) must have non-empty alt text (=caption).
    image_refs = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text)
    assert image_refs, "no image references found"
    for alt, path in image_refs:
        assert alt.strip(), f"image {path} missing caption"


def test_byte_identical_re_run(tmp_path: Path) -> None:
    out1 = tmp_path / "r1.md"
    out2 = tmp_path / "r2.md"
    payload = dict(
        manifest=_manifest(top3=["motivation"]),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={"top3_axes": ["motivation"], "prescriptive_text": "x"},
        fig3_path=Path("figs/fig3.png"),
        fig4_path=Path("figs/fig4.png"),
    )
    build_us1_report(**payload, out_path=out1)
    build_us1_report(**payload, out_path=out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nest" / "report.md"
    build_us1_report(
        manifest=_manifest(),
        correlation_cells=_cells(),
        regression_coefs=_coefs(),
        regression_fit=_fit(),
        recommendations={"top3_axes": [], "prescriptive_text": ""},
        fig3_path=Path("figs/fig3.png"),
        fig4_path=Path("figs/fig4.png"),
        out_path=nested,
    )
    assert nested.exists()


def test_empty_correlation_cells_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        build_us1_report(
            manifest=_manifest(),
            correlation_cells=[],
            regression_coefs=_coefs(),
            regression_fit=_fit(),
            recommendations={"top3_axes": [], "prescriptive_text": ""},
            fig3_path=Path("figs/fig3.png"),
            fig4_path=Path("figs/fig4.png"),
            out_path=tmp_path / "report.md",
        )
