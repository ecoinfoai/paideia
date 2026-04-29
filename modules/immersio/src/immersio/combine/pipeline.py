"""Phase 3 pipeline orchestration (T033, US1 partial mode).

INTEGRATION (RULE 4 active 진입점, 2026-04-30):
- joiner / silver_writer / correlation / regression / recommendations /
  figures / report_md / report_pdf / xlsx_writer / manifest 모두 본 모듈
  에서 호출됨 (orchestrator: combine/pipeline.py, change: add-call,
  task: T033).
- 후속 phase (US2 T042, US4 T056, US5 T047, US6 T060) 가 본 entry-point
  를 확장하여 4 시트 / 4 figs / cluster_compare / subgroup_compare /
  archival 통합.

US1 partial mode 산출:
- silver: `진단×시험결합.parquet` + `manifest_phase3.json`
- gold: `결합분석보고서.md` + `결합분석보고서.pdf` +
  `결합분석.xlsx` (2 시트) + `figs/fig{3,4}_*.png`

Determinism (research §R13 vectors 1+2+3+4+5+6+7+8 모두 통합):
- vector #1 sort_keys (manifest + silver dict 컬럼)
- vector #2 pyarrow flags (silver_writer)
- vector #3 SOURCE_DATE_EPOCH (report_pdf)
- vector #4 PNG metadata (figures)
- vector #5 dcterms:modified (xlsx_writer)
- vector #6 row order (joiner + silver_writer)
- vector #7 BH-FDR stable sort (fdr)
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq

from .correlation import compute_correlation_matrix
from .figures import render_fig3_heatmap, render_fig4_beta_bar
from .joiner import join_silver_phase3
from .manifest import compute_input_sha256, write_manifest
from .recommendations import build_recommendations
from .regression import compute_ols_regression
from .report_md import build_us1_report
from .report_pdf import render_combined_analysis_pdf
from .silver_writer import write_combined_silver
from .xlsx_writer import write_us1_xlsx

from paideia_shared.schemas import CombinedAnalysisManifest

_GENERATED_AT_UTC = "2026-04-30T00:00:00Z"


def _load_inputs(silver_dir: Path, semester: str, course_slug: str) -> dict:
    nm = silver_dir / "needs-map" / f"{semester}-{course_slug}"
    im = silver_dir / "immersio" / f"{semester}-{course_slug}"
    cluster_names_raw = json.loads(
        (nm / "cluster_names.json").read_text(encoding="utf-8")
    )
    cluster_names = {int(k): v for k, v in cluster_names_raw.items()}
    return {
        "nm_dir": nm,
        "im_dir": im,
        "student_master": pq.read_table(im / "student_master.parquet").to_pandas(),
        "factor_scores": pq.read_table(nm / "factor_scores.parquet").to_pandas(),
        "cluster_assignment": pq.read_table(
            nm / "cluster_assignment.parquet"
        ).to_pandas(),
        "cluster_names": cluster_names,
        "student_metrics": pq.read_table(im / "학생지표.parquet").to_pandas(),
        "diagnostic_response": pq.read_table(
            im / "diagnostic_response.parquet"
        ).to_pandas(),
    }


def run_us1_pipeline(
    *,
    semester: str,
    course_slug: str,
    silver_dir: Path,
    gold_dir: Path,
) -> int:
    """Run the US1 partial Phase 3 pipeline.

    Args:
        semester: Academic semester code (e.g. "2026-1").
        course_slug: Course slug (e.g. "anatomy").
        silver_dir: Silver root containing ``needs-map/`` and
            ``immersio/`` subdirectories.
        gold_dir: Gold root for report/xlsx/figs output.

    Returns:
        Exit code (0 on success). FR-024 exit codes 2-6 are surfaced by
        T047 cli wrapper; this function lets exceptions propagate so
        cli.py can map them.
    """
    inputs = _load_inputs(silver_dir, semester, course_slug)

    # 1. joiner — left-join + R-10 audit
    df, counts = join_silver_phase3(
        student_master=inputs["student_master"],
        factor_scores=inputs["factor_scores"],
        cluster_assignment=inputs["cluster_assignment"],
        cluster_names=inputs["cluster_names"],
        student_metrics=inputs["student_metrics"],
        diagnostic_response=inputs["diagnostic_response"],
    )

    # 2. silver_writer — 진단×시험결합.parquet
    silver_target = inputs["im_dir"] / "진단×시험결합.parquet"
    write_combined_silver(df, silver_target)

    # 3. correlation
    correlation_cells = compute_correlation_matrix(df)

    # 4. regression — drops if complete-case n < 9 (raises ValueError)
    regression_coefs, regression_fit = compute_ols_regression(df)

    # 5. recommendations
    recommendations = build_recommendations(regression_coefs, regression_fit)

    # 6. gold output paths
    gold_target = gold_dir / "immersio" / f"{semester}-{course_slug}"
    figs_dir = gold_target / "figs"
    fig3_path = figs_dir / "fig3_corr_heatmap.png"
    fig4_path = figs_dir / "fig4_beta_bar.png"

    # 7. figures
    render_fig3_heatmap(correlation_cells, fig3_path)
    render_fig4_beta_bar(regression_coefs, fig4_path)

    # 8. manifest — partition counts + R-10 audit + 6 sha256
    n_dx = int(((df["진단응답"]) & (~df["시험응시"])).sum())
    n_ex = int(((~df["진단응답"]) & (df["시험응시"])).sum())
    n_both = int(((df["진단응답"]) & (df["시험응시"])).sum())
    n_neither = int(((~df["진단응답"]) & (~df["시험응시"])).sum())

    manifest = CombinedAnalysisManifest(
        schema_version="0.1.0",
        module_version="immersio/0.1.0",
        semester=semester,
        course_slug=course_slug,
        generated_at_utc=_GENERATED_AT_UTC,
        factor_scores_sha256=compute_input_sha256(
            inputs["nm_dir"] / "factor_scores.parquet"
        ),
        cluster_assignment_sha256=compute_input_sha256(
            inputs["nm_dir"] / "cluster_assignment.parquet"
        ),
        cluster_names_sha256=compute_input_sha256(
            inputs["nm_dir"] / "cluster_names.json"
        ),
        student_metrics_sha256=compute_input_sha256(
            inputs["im_dir"] / "학생지표.parquet"
        ),
        student_master_sha256=compute_input_sha256(
            inputs["im_dir"] / "student_master.parquet"
        ),
        diagnostic_response_sha256=compute_input_sha256(
            inputs["im_dir"] / "diagnostic_response.parquet"
        ),
        n_students_combined=len(df),
        n_diagnostic_only=n_dx,
        n_exam_only=n_ex,
        n_both=n_both,
        n_neither=n_neither,
        n_unmatched_factor_scores=counts.unmatched_factor_scores,
        n_unmatched_cluster_assignment=counts.unmatched_cluster_assignment,
        n_unmatched_student_metrics=counts.unmatched_student_metrics,
        n_off_roster_respondents=counts.off_roster_respondents,
        ruleset_version="0.1.0",
        regression_method="OLS",
        multiple_comparison_method="BH-FDR",
        # US1 partial mode does not run cluster_compare; mark posthoc N/A.
        posthoc_method_used="N/A",
        run_seed=0,
        needs_map_schema_version="1.1.0",
        immersio_phase2_schema_version="0.1.0",
        top3_predictor_axes=list(recommendations["top3_axes"]),
    )
    write_manifest(manifest, inputs["im_dir"] / "manifest_phase3.json")

    # 9. report_md (4 sections + §4/§5 placeholder)
    md_path = gold_target / "결합분석보고서.md"
    build_us1_report(
        manifest=manifest,
        correlation_cells=correlation_cells,
        regression_coefs=regression_coefs,
        regression_fit=regression_fit,
        recommendations=recommendations,
        # Markdown image paths use the figs/ relative form for the gold
        # tree so PDF/MD readers resolve them naturally.
        fig3_path=Path("figs/fig3_corr_heatmap.png"),
        fig4_path=Path("figs/fig4_beta_bar.png"),
        out_path=md_path,
    )

    # 10. report_pdf (uses md_text + image_base_dir=gold_target so figs/
    #     resolves)
    md_text = md_path.read_text(encoding="utf-8")
    render_combined_analysis_pdf(
        md_text=md_text,
        output_path=gold_target / "결합분석보고서.pdf",
        created_at_utc=_GENERATED_AT_UTC,
        image_base_dir=gold_target,
    )

    # 11. xlsx (2 sheets US1 mode)
    write_us1_xlsx(
        correlation_cells=correlation_cells,
        regression_coefs=regression_coefs,
        regression_fit=regression_fit,
        out_path=gold_target / "결합분석.xlsx",
    )

    return 0


__all__ = ["run_us1_pipeline"]
